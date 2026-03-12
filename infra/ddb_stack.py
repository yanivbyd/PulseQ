from dataclasses import dataclass

from aws_cdk import RemovalPolicy, aws_dynamodb as dynamodb
from constructs import Construct


@dataclass
class Tables:
    topics_table: dynamodb.Table
    articles_table: dynamodb.Table
    user_inbox_table: dynamodb.Table


def create_ddb_tables(scope: Construct) -> Tables:
    topics_table = dynamodb.Table(
        scope,
        "TopicsTable",
        table_name="pulseq-topics",
        partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        removal_policy=RemovalPolicy.RETAIN,
    )

    articles_table = dynamodb.Table(
        scope,
        "ArticlesTableV2",
        table_name="pulseq-articles",
        partition_key=dynamodb.Attribute(name="articleId", type=dynamodb.AttributeType.STRING),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        removal_policy=RemovalPolicy.RETAIN,
    )

    user_inbox_table = dynamodb.Table(
        scope,
        "UserInboxTable",
        table_name="pulseq-user-inbox",
        partition_key=dynamodb.Attribute(name="userId", type=dynamodb.AttributeType.STRING),
        sort_key=dynamodb.Attribute(name="articleId", type=dynamodb.AttributeType.STRING),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        removal_policy=RemovalPolicy.RETAIN,
    )

    return Tables(
        topics_table=topics_table,
        articles_table=articles_table,
        user_inbox_table=user_inbox_table,
    )
