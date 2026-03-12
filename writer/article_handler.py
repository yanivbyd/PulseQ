import logging
import os
import random
from datetime import datetime, timezone

import boto3

# In Lambda the bundle root contains sibling modules.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from writer import generate_article, generate_follow_up_article  # Lambda environment
    from handler_utils import AWS_REGION, get_openai_api_key, s3_get_text
except ImportError:
    from writer.writer import generate_article, generate_follow_up_article  # type: ignore[no-redef]  # Test environment
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


def load_follow_up_instructions(s3, bucket: str) -> str:
    try:
        return s3_get_text(s3, bucket, "shared/follow_up_article_instructions.txt")
    except Exception as e:
        logger.error("article-handler: failed to load follow-up instructions from S3: %s", e)
        raise


def load_original_article_html(ddb, article_id: str) -> str:
    try:
        articles_table = ddb.Table(os.environ["ARTICLES_TABLE"])
        result = articles_table.get_item(Key={"articleId": article_id})
        item = result.get("Item")
        if not item:
            raise ValueError(f"article not found: {article_id}")
        return item["html"]
    except Exception as e:
        logger.error("article-handler: failed to load original article from DDB: %s", e)
        raise


def load_user_tastes(s3, bucket: str, user_id: str) -> str:
    try:
        return s3_get_text(s3, bucket, f"{user_id}/user_tastes.md")
    except Exception as e:
        logger.error("article-handler: failed to load user tastes from S3: %s", e)
        raise


def pick_topic(ddb, user_id: str) -> tuple[str, dict, list[dict]]:
    try:
        topics_table = ddb.Table(os.environ["TOPICS_TABLE"])
        resp = topics_table.get_item(Key={"userId": user_id})
        topics: list[dict] = resp.get("Item", {}).get("topics", [])
        if not topics:
            raise ValueError("no topics found for user")
        chosen = random.choice(topics)
        return f"{chosen['title']} — {chosen['description']}", chosen, topics
    except Exception as e:
        logger.error("article-handler: failed to load topics: %s", e)
        raise


def write_article(topic: str, article_instructions: str, user_tastes: str) -> dict:
    try:
        return generate_article(topic=topic, article_instructions=article_instructions, user_tastes=user_tastes)
    except Exception as e:
        logger.error("article-handler: generate_article failed: %s", e)
        raise


def save_article(ddb, article_id: str, user_id: str, article: dict, creation_timestamp: str, source_article_id: str | None = None) -> None:
    try:
        article_item: dict = {
            "articleId": article_id,
            "userId": user_id,
            "title": article["title"],
            "html": article["html"],
            "creation_timestamp": creation_timestamp,
        }
        if source_article_id is not None:
            article_item["sourceArticleId"] = source_article_id
        ddb.Table(os.environ["ARTICLES_TABLE"]).put_item(Item=article_item)
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


def consume_topic(ddb, user_id: str, chosen: dict, topics: list[dict]) -> None:
    try:
        topics_table = ddb.Table(os.environ["TOPICS_TABLE"])
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

    follow_up_article_id = event.get("followUpArticleId")
    follow_up_extra_context = event.get("followUpExtraContext")
    custom_topic = event.get("customTopic")

    api_key = load_api_key()
    os.environ["OPENAI_API_KEY"] = api_key

    s3 = boto3.client("s3", region_name=AWS_REGION)
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)

    user_tastes = load_user_tastes(s3, os.environ["INPUT_BUCKET"], user_id)

    if follow_up_article_id:
        follow_up_instructions = load_follow_up_instructions(s3, os.environ["INPUT_BUCKET"])
        original_html = load_original_article_html(ddb, follow_up_article_id)
        article = generate_follow_up_article(original_html, follow_up_extra_context, user_tastes, follow_up_instructions)
        save_article(ddb, article["id"], user_id, article, now_utc_iso(), source_article_id=follow_up_article_id)
    else:
        article_instructions = load_instructions(s3, os.environ["INPUT_BUCKET"])
        if custom_topic:
            article = write_article(custom_topic, article_instructions, user_tastes)
        else:
            topic, chosen, topics = pick_topic(ddb, user_id)
            article = write_article(topic, article_instructions, user_tastes)
            consume_topic(ddb, user_id, chosen, topics)
        save_article(ddb, article["id"], user_id, article, now_utc_iso())

    return {"articleId": article["id"], "userId": user_id, "articleTitle": article["title"]}
