import logging
import os
import random
from datetime import datetime, timezone

import boto3

# In Lambda the bundle root contains sibling modules.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from writer import generate_article  # Lambda environment
    from handler_utils import AWS_REGION, get_openai_api_key, s3_get_text
except ImportError:
    from writer.writer import generate_article  # type: ignore[no-redef]  # Test environment
    from writer.handler_utils import AWS_REGION, get_openai_api_key, s3_get_text  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def load_api_key() -> str:
    try:
        return get_openai_api_key()
    except Exception as e:
        logger.error("article-handler: failed to retrieve secret: %s", e)
        raise


def load_instructions(s3, bucket: str) -> str:
    try:
        return s3_get_text(s3, bucket, "shared/article_generation_instructions.txt")
    except Exception as e:
        logger.error("article-handler: failed to load instructions from S3: %s", e)
        raise


def pick_topic(topics_table, user_id: str) -> tuple[str, dict, list[dict]]:
    try:
        resp = topics_table.get_item(Key={"userId": user_id})
        topics: list[dict] = resp.get("Item", {}).get("topics", [])
        if not topics:
            raise ValueError("no topics found for user")
        chosen = random.choice(topics)
        return f"{chosen['title']} — {chosen['description']}", chosen, topics
    except Exception as e:
        logger.error("article-handler: failed to load topics: %s", e)
        raise


def write_article(topic: str, article_instructions: str) -> dict:
    try:
        return generate_article(topic=topic, article_instructions=article_instructions)
    except Exception as e:
        logger.error("article-handler: generate_article failed: %s", e)
        raise


def save_article(ddb, article_id: str, user_id: str, article: dict, creation_timestamp: str) -> None:
    try:
        ddb.Table(os.environ["ARTICLES_TABLE"]).put_item(Item={
            "articleId": article_id,
            "userId": user_id,
            "title": article["title"],
            "html": article["html"],
            "creation_timestamp": creation_timestamp,
        })
        ddb.Table(os.environ["USER_INBOX_TABLE"]).put_item(Item={
            "userId": user_id,
            "articleId": article_id,
            "title": article["title"],
            "creation_timestamp": creation_timestamp,
        })
    except Exception as e:
        logger.error("article-handler: failed to save article to DDB: %s", e)
        raise


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def consume_topic(topics_table, user_id: str, chosen: dict, topics: list[dict]) -> None:
    try:
        remaining = [t for t in topics if t["title"] != chosen["title"]]
        topics_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET topics = :topics",
            ConditionExpression="topics = :orig",
            ExpressionAttributeValues={":topics": remaining, ":orig": topics},
        )
    except Exception as e:
        logger.warning("article-handler: failed to remove consumed topic: %s", e)


def handler(event, context):
    user_id = event.get("userId")
    if not user_id:
        logger.error("article-handler: missing userId in event")
        raise ValueError("userId is required")

    custom_topic = event.get("customTopic")

    api_key = load_api_key()
    os.environ["OPENAI_API_KEY"] = api_key

    s3 = boto3.client("s3", region_name=AWS_REGION)
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)

    article_instructions = load_instructions(s3, os.environ["INPUT_BUCKET"])

    if custom_topic:
        topic = custom_topic
        article = write_article(topic, article_instructions)
    else:
        topics_table = ddb.Table(os.environ["TOPICS_TABLE"])
        topic, chosen, topics = pick_topic(topics_table, user_id)
        article = write_article(topic, article_instructions)
        consume_topic(topics_table, user_id, chosen, topics)

    save_article(ddb, article["id"], user_id, article, now_utc_iso())

    return {"articleId": article["id"], "userId": user_id, "articleTitle": article["title"]}
