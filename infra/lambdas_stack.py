from dataclasses import dataclass

from aws_cdk import (
    BundlingOptions,
    Duration,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_lambda_nodejs as nodejs,
    aws_s3 as s3,
)
from constructs import Construct

from ddb_stack import Tables
from secrets_stack import Secrets


@dataclass
class Lambdas:
    topic_selector_fn: _lambda.Function
    tavily_fn: _lambda.Function
    article_fn: _lambda.Function
    quiz_fn: _lambda.Function
    notification_fn: _lambda.Function
    scout_fn: _lambda.Function
    web_fn: nodejs.NodejsFunction
    mcp_fn: _lambda.Function


def create_lambdas(
    scope: Construct,
    input_bucket: s3.IBucket,
    events_bucket: s3.IBucket,
    ddb_tables: Tables,
    secrets: Secrets,
) -> Lambdas:
    py_bundling = BundlingOptions(
        image=_lambda.Runtime.PYTHON_3_12.bundling_image,
        command=[
            "bash",
            "-c",
            "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
        ],
    )

    # ── Writer Lambdas ───────────────────────────────────────────────────────
    topic_selector_fn = _lambda.Function(
        scope,
        "TopicSelectorFunction",
        runtime=_lambda.Runtime.PYTHON_3_12,
        architecture=_lambda.Architecture.ARM_64,
        handler="topic_selector_handler.handler",
        code=_lambda.Code.from_asset("../writer", bundling=py_bundling),
        timeout=Duration.minutes(15),
        environment={
            "TOPICS_TABLE": ddb_tables.topics_table.table_name,
            "ARTICLES_TABLE": ddb_tables.articles_table.table_name,
        },
    )
    ddb_tables.topics_table.grant(topic_selector_fn, "dynamodb:GetItem", "dynamodb:UpdateItem")
    ddb_tables.articles_table.grant(topic_selector_fn, "dynamodb:GetItem")

    tavily_fn = _lambda.Function(
        scope,
        "TavilyFunction",
        runtime=_lambda.Runtime.PYTHON_3_12,
        architecture=_lambda.Architecture.ARM_64,
        handler="tavily_handler.handler",
        code=_lambda.Code.from_asset("../writer", bundling=py_bundling),
        timeout=Duration.minutes(15),
        environment={
            "TAVILY_SECRET_NAME": secrets.tavily.secret_name,
        },
    )
    secrets.tavily.grant_read(tavily_fn)

    article_fn = _lambda.Function(
        scope,
        "ArticleFunction",
        runtime=_lambda.Runtime.PYTHON_3_12,
        architecture=_lambda.Architecture.ARM_64,
        handler="article_handler.handler",
        code=_lambda.Code.from_asset("../writer", bundling=py_bundling),
        timeout=Duration.minutes(15),
        environment={
            "INPUT_BUCKET": input_bucket.bucket_name,
            "SECRET_NAME": secrets.openai.secret_name,
            "ARTICLES_TABLE": ddb_tables.articles_table.table_name,
            "USER_INBOX_TABLE": ddb_tables.user_inbox_table.table_name,
        },
    )
    input_bucket.grant_read(article_fn)
    secrets.openai.grant_read(article_fn)
    ddb_tables.articles_table.grant(article_fn, "dynamodb:PutItem", "dynamodb:GetItem")
    ddb_tables.user_inbox_table.grant(article_fn, "dynamodb:PutItem")

    quiz_fn = _lambda.Function(
        scope,
        "QuizFunction",
        runtime=_lambda.Runtime.PYTHON_3_12,
        architecture=_lambda.Architecture.ARM_64,
        handler="quiz_handler.handler",
        code=_lambda.Code.from_asset("../writer", bundling=py_bundling),
        timeout=Duration.minutes(15),
        environment={
            "INPUT_BUCKET": input_bucket.bucket_name,
            "SECRET_NAME": secrets.openai.secret_name,
            "ARTICLES_TABLE": ddb_tables.articles_table.table_name,
        },
    )
    input_bucket.grant_read(quiz_fn)
    secrets.openai.grant_read(quiz_fn)
    ddb_tables.articles_table.grant(quiz_fn, "dynamodb:GetItem", "dynamodb:UpdateItem")

    notification_fn = _lambda.Function(
        scope,
        "NotificationFunction",
        runtime=_lambda.Runtime.PYTHON_3_12,
        architecture=_lambda.Architecture.ARM_64,
        handler="notification_handler.handler",
        code=_lambda.Code.from_asset("../writer", bundling=py_bundling),
        timeout=Duration.minutes(15),
        environment={
            "IFTTT_SECRET_NAME": secrets.ifttt.secret_name,
        },
    )
    secrets.ifttt.grant_read(notification_fn)

    # ── Scout Lambda ─────────────────────────────────────────────────────────
    scout_fn = _lambda.Function(
        scope,
        "ScoutFunction",
        runtime=_lambda.Runtime.PYTHON_3_12,
        architecture=_lambda.Architecture.ARM_64,
        handler="lambda_handler.handler",
        code=_lambda.Code.from_asset("../scout", bundling=py_bundling),
        timeout=Duration.minutes(15),
        environment={
            "INPUT_BUCKET": input_bucket.bucket_name,
            "EVENTS_BUCKET": events_bucket.bucket_name,
            "SECRET_NAME": secrets.openai.secret_name,
            "TOPICS_TABLE": ddb_tables.topics_table.table_name,
        },
    )
    input_bucket.grant_read(scout_fn)
    events_bucket.grant_read(scout_fn)
    secrets.openai.grant_read(scout_fn)
    ddb_tables.topics_table.grant_read_write_data(scout_fn)

    # ── Backend Lambda (Node.js) ──────────────────────────────────────────────
    web_fn = nodejs.NodejsFunction(
        scope,
        "WebFunction",
        entry="../backend/index.ts",
        handler="handler",
        runtime=_lambda.Runtime.NODEJS_22_X,
        architecture=_lambda.Architecture.ARM_64,
        timeout=Duration.seconds(10),
        environment={
            "ARTICLES_TABLE": ddb_tables.articles_table.table_name,
            "USER_INBOX_TABLE": ddb_tables.user_inbox_table.table_name,
            "TOPICS_TABLE": ddb_tables.topics_table.table_name,
        },
        bundling=nodejs.BundlingOptions(
            external_modules=["@aws-sdk/*"],
        ),
    )
    ddb_tables.articles_table.grant(web_fn, "dynamodb:GetItem")
    ddb_tables.user_inbox_table.grant(web_fn, "dynamodb:Query", "dynamodb:DeleteItem")
    ddb_tables.topics_table.grant_read_data(web_fn)
    scout_fn.grant_invoke(web_fn)
    events_bucket.grant_put(web_fn)
    web_fn.add_environment("SCOUT_FUNCTION_ARN", scout_fn.function_arn)
    web_fn.add_environment("EVENTS_BUCKET", events_bucket.bucket_name)

    # ── MCP Server Lambda ─────────────────────────────────────────────────────
    mcp_fn = _lambda.Function(
        scope,
        "McpServerFunction",
        runtime=_lambda.Runtime.PYTHON_3_12,
        architecture=_lambda.Architecture.ARM_64,
        handler="lambda_handler.handler",
        code=_lambda.Code.from_asset("../mcp_server", bundling=py_bundling),
        timeout=Duration.seconds(30),
        environment={
            "USER_ID": "user1",
        },
    )

    return Lambdas(
        topic_selector_fn=topic_selector_fn,
        tavily_fn=tavily_fn,
        article_fn=article_fn,
        quiz_fn=quiz_fn,
        notification_fn=notification_fn,
        scout_fn=scout_fn,
        web_fn=web_fn,
        mcp_fn=mcp_fn,
    )
