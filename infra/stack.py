import json

from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cf_origins,
    aws_iam as iam,
    aws_s3 as s3,
    aws_scheduler as scheduler,
    aws_secretsmanager as sm,
)
from constructs import Construct

from ddb_stack import create_ddb_tables
from lambdas_stack import create_lambdas
from writer_pipeline_stack import create_writer_pipeline


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

        # ── DynamoDB tables ──────────────────────────────────────────────────
        ddb_tables = create_ddb_tables(self)

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

        # ── S3: events (user feedback and future UI events) ──────────────────
        events_bucket = s3.Bucket(
            self,
            "EventsBucket",
            bucket_name="pulseq-events",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── Lambdas ──────────────────────────────────────────────────────────
        lambdas = create_lambdas(
            self,
            input_bucket=input_bucket,
            events_bucket=events_bucket,
            ddb_tables=ddb_tables,
            secret=secret,
            ifttt_secret=ifttt_secret,
        )

        # ── Step Functions: WriterStateMachine ───────────────────────────────
        writer_state_machine = create_writer_pipeline(
            self,
            article_fn=lambdas.article_fn,
            quiz_fn=lambdas.quiz_fn,
            notification_fn=lambdas.notification_fn,
        )

        # ── Cross-cutting wiring (state machine ↔ lambdas) ──────────────────
        writer_state_machine.grant_start_execution(lambdas.web_fn)
        lambdas.web_fn.add_environment("WRITER_STATE_MACHINE_ARN", writer_state_machine.state_machine_arn)

        writer_state_machine.grant_start_execution(lambdas.mcp_fn)
        lambdas.mcp_fn.add_environment("WRITER_STATE_MACHINE_ARN", writer_state_machine.state_machine_arn)

        # ── API Gateway HTTP API (backend) ───────────────────────────────────
        web_api = apigwv2.HttpApi(self, "WebApi")
        web_integration = integrations.HttpLambdaIntegration("WebIntegration", lambdas.web_fn)
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

        lambdas.notification_fn.add_environment("WEB_BASE_URL", f"https://{frontend_distribution.domain_name}")

        CfnOutput(self, "FrontendUrl", value=f"https://{frontend_distribution.domain_name}")
        CfnOutput(self, "BackendApiUrl", value=web_api.api_endpoint)

        # ── MCP API Gateway ──────────────────────────────────────────────────
        mcp_api = apigwv2.HttpApi(self, "McpHttpApi")
        mcp_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=integrations.HttpLambdaIntegration("McpIntegration", lambdas.mcp_fn),
        )

        # Apply throttling to the auto-created $default stage via L1 escape hatch
        mcp_api.default_stage.node.default_child.add_override(
            "Properties.DefaultRouteSettings",
            {"ThrottlingRateLimit": 5, "ThrottlingBurstLimit": 10},
        )

        CfnOutput(self, "McpEndpointUrl", value=mcp_api.url or "")

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
                            resources=[lambdas.scout_fn.function_arn],
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
                arn=lambdas.scout_fn.function_arn,
                role_arn=scout_scheduler_role.role_arn,
                input=json.dumps({"userId": "user1"}),
            ),
        )

        # ── Daily scheduler: start WriterStateMachine at 08:00 Asia/Jerusalem ─
        scheduler_role = iam.Role(
            self,
            "SchedulerRole",
            assumed_by=iam.ServicePrincipal("scheduler.amazonaws.com"),
            inline_policies={
                "StartWriterExecution": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["states:StartExecution"],
                            resources=[writer_state_machine.state_machine_arn],
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
                arn=writer_state_machine.state_machine_arn,
                role_arn=scheduler_role.role_arn,
                input=json.dumps({"userId": "user1"}),
            ),
        )
