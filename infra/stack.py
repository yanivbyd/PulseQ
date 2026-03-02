from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_lambda as _lambda,
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

        # ── S3: output (public static website) ─────────────────────────────
        output_bucket = s3.Bucket(
            self,
            "OutputBucket",
            bucket_name="pulseq",
            website_index_document="index.html",
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
            removal_policy=RemovalPolicy.RETAIN,
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

        # ── Lambda ──────────────────────────────────────────────────────────
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
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "SECRET_NAME": secret.secret_name,
                "IFTTT_SECRET_NAME": ifttt_secret.secret_name,
            },
        )

        # ── IAM permissions ─────────────────────────────────────────────────
        input_bucket.grant_read(writer_fn)
        output_bucket.grant_put(writer_fn)
        secret.grant_read(writer_fn)
        ifttt_secret.grant_read(writer_fn)

        # ── API Gateway HTTP API ─────────────────────────────────────────────
        http_api = apigwv2.HttpApi(self, "WriterApi")
        http_api.add_routes(
            path="/run",
            methods=[apigwv2.HttpMethod.POST],
            integration=integrations.HttpLambdaIntegration(
                "WriterIntegration", writer_fn
            ),
        )

        CfnOutput(self, "ApiUrl", value=f"{http_api.api_endpoint}/run")
