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


def handler(event, context):
    user_id = event.get("userId")
    if not user_id:
        logger.error("article-handler: missing userId in event")
        raise ValueError("userId is required")

    try:
        api_key = get_openai_api_key()
    except Exception as e:
        logger.error("article-handler: failed to retrieve secret: %s", e)
        raise

    os.environ["OPENAI_API_KEY"] = api_key

    s3 = boto3.client("s3", region_name=AWS_REGION)
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    topics_table = ddb.Table(os.environ["TOPICS_TABLE"])

    try:
        article_instructions = s3_get_text(
            s3, os.environ["INPUT_BUCKET"], "shared/article_generation_instructions.txt"
        )
    except Exception as e:
        logger.error("article-handler: failed to load instructions from S3: %s", e)
        raise

    try:
        resp = topics_table.get_item(Key={"userId": user_id})
        topics: list[dict] = resp.get("Item", {}).get("topics", [])
        if not topics:
            raise ValueError("no topics found for user")
        chosen = random.choice(topics)
        topic = f"{chosen['title']} — {chosen['description']}"
    except Exception as e:
        logger.error("article-handler: failed to load topics: %s", e)
        raise

    try:
        article = generate_article(topic=topic, article_instructions=article_instructions)
    except Exception as e:
        logger.error("article-handler: generate_article failed: %s", e)
        raise

    creation_timestamp = (
        datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
    articles_table = ddb.Table(os.environ["ARTICLES_TABLE"])
    try:
        articles_table.put_item(Item={
            "userid": user_id,
            "creation_timestamp": creation_timestamp,
            "id": article["id"],
            "title": article["title"],
            "accent": article["accent"],
            "html": article["html"],
        })
    except Exception as e:
        logger.error("article-handler: failed to save article to DDB: %s", e)
        raise

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

    return {"articleId": article["id"], "userId": user_id, "articleTitle": article["title"]}
