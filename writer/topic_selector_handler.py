import logging
import os
import random

import boto3

try:
    from writer import generate_short_id  # Lambda environment
    from handler_utils import AWS_REGION
    from workflow_state import WorkflowState
except ImportError:
    from writer.writer import generate_short_id  # type: ignore[no-redef]  # Test environment
    from writer.handler_utils import AWS_REGION  # type: ignore[no-redef]
    from writer.workflow_state import WorkflowState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def pick_and_consume_topic(ddb, user_id: str) -> str:
    """Pick a random topic from the pool, consume it, and return the topic string."""
    topics_table = ddb.Table(os.environ["TOPICS_TABLE"])
    resp = topics_table.get_item(Key={"userId": user_id})
    topics: list[dict] = resp.get("Item", {}).get("topics", [])
    if not topics:
        raise ValueError("no topics found for user")
    chosen = random.choice(topics)
    remaining = [t for t in topics if t["title"] != chosen["title"]]
    topics_table.update_item(
        Key={"userId": user_id},
        UpdateExpression="SET topics = :topics",
        ConditionExpression="topics = :orig",
        ExpressionAttributeValues={":topics": remaining, ":orig": topics},
    )
    return f"{chosen['title']} — {chosen['description']}"


def get_article_title(ddb, article_id: str) -> str:
    """Read the title of an existing article from DynamoDB."""
    articles_table = ddb.Table(os.environ["ARTICLES_TABLE"])
    result = articles_table.get_item(Key={"articleId": article_id})
    item = result.get("Item")
    if not item:
        raise ValueError(f"article not found: {article_id}")
    return item["title"]


def handler(event, context):
    state = WorkflowState.from_event(event)

    if not state.userId:
        logger.error("topic-selector: missing userId in event")
        raise ValueError("userId is required")

    if state.customTopic and state.followUpArticleId:
        logger.error("topic-selector: customTopic and followUpArticleId are mutually exclusive")
        raise ValueError("customTopic and followUpArticleId are mutually exclusive")

    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)

    try:
        if state.customTopic:
            article_topic = state.customTopic
        elif state.followUpArticleId:
            original_title = get_article_title(ddb, state.followUpArticleId)
            article_topic = f"{original_title} — {state.extraContent}" if state.extraContent else original_title
        else:
            article_topic = pick_and_consume_topic(ddb, state.userId)
    except Exception as e:
        logger.error("topic-selector: failed to resolve article topic: %s", e)
        raise

    return WorkflowState(
        userId=state.userId,
        articleId=generate_short_id(),
        articleTopic=article_topic,
        followUpArticleId=state.followUpArticleId,
        extraContent=state.extraContent,
    ).to_dict()
