import json
import os

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cf_origins,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_lambda_nodejs as nodejs,
    aws_s3 as s3,
    aws_scheduler as scheduler,
    aws_secretsmanager as sm,
)
from constructs import Construct


class WriterStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3: inputs (private) ────────────────────────────────────────────
        input_bucket = s3.Bucket(
            self,
            "InputBucket",
            bucket_name="pulseq-inputs",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── S3: React SPA (private — served via CloudFront) ─────────────────
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name="pulseq-frontend",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: topics ─────────────────────────────────────────────────
        topics_table = dynamodb.Table(
            self,
            "TopicsTable",
            table_name="pulseq-topics",
            partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: articles ───────────────────────────────────────────────
        articles_table = dynamodb.Table(
            self,
            "ArticlesTable",
            table_name="pulseq-articles",
            partition_key=dynamodb.Attribute(name="userid", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="creation_timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
        articles_table.add_global_secondary_index(
            index_name="ById",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── Secrets Manager ─────────────────────────────────────────────────
        secret = sm.Secret(
            self,
            "OpenAIApiKey",
            secret_name="pulseq/openai-api-key",
            description="OpenAI API key",
        )

        ifttt_secret = sm.Secret.from_secret_name_v2(
            self,
            "IftttKey",
            "pulseq/ifttt-key",
        )

        # ── Writer Lambda ────────────────────────────────────────────────────
        writer_fn = _lambda.Function(
            self,
            "WriterFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            handler="lambda_handler.handler",
            code=_lambda.Code.from_asset(
                "../writer",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            timeout=Duration.minutes(5),
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "SECRET_NAME": secret.secret_name,
                "IFTTT_SECRET_NAME": ifttt_secret.secret_name,
                "ARTICLES_TABLE": articles_table.table_name,
                "TOPICS_TABLE": topics_table.table_name,
            },
        )

        # ── IAM permissions ─────────────────────────────────────────────────
        input_bucket.grant_read(writer_fn)
        secret.grant_read(writer_fn)
        ifttt_secret.grant_read(writer_fn)
        articles_table.grant(writer_fn, "dynamodb:PutItem")
        topics_table.grant_read_data(writer_fn)

        # ── API Gateway HTTP API (writer) ────────────────────────────────────
        http_api = apigwv2.HttpApi(self, "WriterApi")
        http_api.add_routes(
            path="/run",
            methods=[apigwv2.HttpMethod.POST],
            integration=integrations.HttpLambdaIntegration(
                "WriterIntegration", writer_fn
            ),
        )

        CfnOutput(self, "ApiUrl", value=f"{http_api.api_endpoint}/run")

        # ── S3: events (user feedback and future UI events) ──────────────────
        events_bucket = s3.Bucket(
            self,
            "EventsBucket",
            bucket_name="pulseq-events",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Scout Lambda ─────────────────────────────────────────────────────
        scout_fn = _lambda.Function(
            self,
            "ScoutFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            handler="lambda_handler.handler",
            code=_lambda.Code.from_asset(
                "../scout",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            timeout=Duration.minutes(15),
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "EVENTS_BUCKET": events_bucket.bucket_name,
                "SECRET_NAME": secret.secret_name,
                "TOPICS_TABLE": topics_table.table_name,
            },
        )

        input_bucket.grant_read(scout_fn)
        events_bucket.grant_read(scout_fn)
        secret.grant_read(scout_fn)
        topics_table.grant_read_write_data(scout_fn)

        # ── Backend Lambda (Node.js — JSON API for articles) ─────────────────
        web_fn = nodejs.NodejsFunction(
            self,
            "WebFunction",
            entry="../backend/index.ts",
            handler="handler",
            runtime=_lambda.Runtime.NODEJS_22_X,
            architecture=_lambda.Architecture.ARM_64,
            timeout=Duration.seconds(10),
            environment={
                "ARTICLES_TABLE": articles_table.table_name,
                "TOPICS_TABLE": topics_table.table_name,
            },
            bundling=nodejs.BundlingOptions(
                external_modules=["@aws-sdk/*"],
            ),
        )
        articles_table.grant(web_fn, "dynamodb:Query", "dynamodb:UpdateItem")
        topics_table.grant_read_data(web_fn)
        writer_fn.grant_invoke(web_fn)
        scout_fn.grant_invoke(web_fn)
        events_bucket.grant_put(web_fn)
        web_fn.add_environment("WRITER_FUNCTION_ARN", writer_fn.function_arn)
        web_fn.add_environment("SCOUT_FUNCTION_ARN", scout_fn.function_arn)
        web_fn.add_environment("EVENTS_BUCKET", events_bucket.bucket_name)

        # ── API Gateway HTTP API (backend) ───────────────────────────────────
        web_api = apigwv2.HttpApi(self, "WebApi")
        web_integration = integrations.HttpLambdaIntegration("WebIntegration", web_fn)
        web_api.add_routes(
            path="/api/article-summaries",
            methods=[apigwv2.HttpMethod.GET],
            integration=web_integration,
        )
        web_api.add_routes(
            path="/api/article/{proxy+}",
            methods=[apigwv2.HttpMethod.GET],
            integration=web_integration,
        )
        web_api.add_routes(
            path="/api/generate",
            methods=[apigwv2.HttpMethod.POST],
            integration=web_integration,
        )
        web_api.add_routes(
            path="/api/mark-read",
            methods=[apigwv2.HttpMethod.POST],
            integration=web_integration,
        )
        web_api.add_routes(
            path="/api/feedback",
            methods=[apigwv2.HttpMethod.POST],
            integration=web_integration,
        )
        web_api.add_routes(
            path="/api/scout",
            methods=[apigwv2.HttpMethod.POST],
            integration=web_integration,
        )
        web_api.add_routes(
            path="/api/topics",
            methods=[apigwv2.HttpMethod.GET],
            integration=web_integration,
        )

        # ── CloudFront: unified distribution (SPA + API) ─────────────────────
        api_domain = f"{web_api.api_id}.execute-api.eu-west-1.amazonaws.com"

        frontend_distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=cf_origins.S3BucketOrigin.with_origin_access_control(frontend_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=cf_origins.HttpOrigin(
                        api_domain,
                        protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                ),
            },
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        writer_fn.add_environment("WEB_BASE_URL", f"https://{frontend_distribution.domain_name}")

        CfnOutput(self, "FrontendUrl", value=f"https://{frontend_distribution.domain_name}")
        CfnOutput(self, "BackendApiUrl", value=web_api.api_endpoint)

        # ── Daily scheduler: invoke Scout Lambda at 07:30 Asia/Jerusalem ─────
        scout_scheduler_role = iam.Role(
            self,
            "ScoutSchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            inline_policies={
                "InvokeScout": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[scout_fn.function_arn],
                        )
                    ]
                )
            },
        )

        scheduler.CfnSchedule(
            self,
            "DailyScoutSchedule",
            schedule_expression="cron(30 7 * * ? *)",
            schedule_expression_timezone="Asia/Jerusalem",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="FLEXIBLE",
                maximum_window_in_minutes=10,
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=scout_fn.function_arn,
                role_arn=scout_scheduler_role.role_arn,
                input=json.dumps({"userId": "user1"}),
            ),
        )

        # ── Daily scheduler: invoke Writer Lambda at 08:00 Asia/Jerusalem ────
        scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            inline_policies={
                "InvokeWriter": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[writer_fn.function_arn],
                        )
                    ]
                )
            },
        )

        scheduler.CfnSchedule(
            self,
            "DailyWriterSchedule",
            schedule_expression="cron(0 8 * * ? *)",
            schedule_expression_timezone="Asia/Jerusalem",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(
                mode="FLEXIBLE",
                maximum_window_in_minutes=30,
            ),
            target=scheduler.CfnSchedule.TargetProperty(
                arn=writer_fn.function_arn,
                role_arn=scheduler_role.role_arn,
                input=json.dumps({"userId": "user1"}),
            ),
        )
