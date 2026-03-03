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
    aws_lambda as _lambda,
    aws_lambda_nodejs as nodejs,
    aws_s3 as s3,
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

        # ── S3: output (private — served via CloudFront) ────────────────────
        output_bucket = s3.Bucket(
            self,
            "OutputBucket",
            bucket_name="pulseq",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
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

        # ── Writer Lambda ──────────────────────────────────────────────────────────
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
            },
        )

        # ── IAM permissions ─────────────────────────────────────────────────
        input_bucket.grant_read(writer_fn)
        secret.grant_read(writer_fn)
        ifttt_secret.grant_read(writer_fn)
        articles_table.grant(writer_fn, "dynamodb:PutItem")

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

        # ── Web Lambda (Node.js — serves articles from DynamoDB) ────────────
        web_fn = nodejs.NodejsFunction(
            self,
            "WebFunction",
            entry="../web_server/index.ts",
            handler="handler",
            runtime=_lambda.Runtime.NODEJS_22_X,
            architecture=_lambda.Architecture.ARM_64,
            timeout=Duration.seconds(10),
            environment={
                "ARTICLES_TABLE": articles_table.table_name,
            },
            bundling=nodejs.BundlingOptions(
                external_modules=["@aws-sdk/*"],
            ),
        )
        articles_table.grant(web_fn, "dynamodb:Query")

        # ── API Gateway HTTP API (web) ───────────────────────────────────────
        web_api = apigwv2.HttpApi(self, "WebApi")
        web_api.add_routes(
            path="/{id}",
            methods=[apigwv2.HttpMethod.GET],
            integration=integrations.HttpLambdaIntegration(
                "WebIntegration", web_fn
            ),
        )

        writer_fn.add_environment("WEB_BASE_URL", web_api.api_endpoint)

        CfnOutput(self, "WebUrl", value=web_api.api_endpoint)

        # ── CloudFront: serves style.css over HTTPS ──────────────────────────
        distribution = cloudfront.Distribution(
            self,
            "StyleDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=cf_origins.S3BucketOrigin.with_origin_access_control(output_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
        )

        CfnOutput(self, "CssUrl", value=f"https://{distribution.domain_name}/style.css")
