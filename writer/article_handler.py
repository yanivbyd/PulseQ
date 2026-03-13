import json
import logging
import os
from datetime import datetime, timezone

import boto3

# In Lambda the bundle root contains sibling modules.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from writer import generate_article, generate_follow_up_article  # Lambda environment
    from handler_utils import AWS_REGION, get_openai_api_key, s3_get_text
    from workflow_state import WorkflowState
except ImportError:
    from writer.writer import generate_article, generate_follow_up_article  # type: ignore[no-redef]  # Test environment
    from writer.handler_utils import AWS_REGION, get_openai_api_key, s3_get_text  # type: ignore[no-redef]
    from writer.workflow_state import WorkflowState  # type: ignore[no-redef]

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


def build_further_reading(tavily_results) -> str:
    try:
        results = tavily_results.get("results", [])
        return json.dumps([{"url": r["url"], "title": r["title"]} for r in results])
    except Exception as e:
        logger.warning("article-handler: failed to build further_reading from tavilyResults: %s", e)
        return "[]"


def save_article(ddb, article_id: str, user_id: str, article: dict, creation_timestamp: str, further_reading: str = "[]", source_article_id: str | None = None) -> None:
    try:
        article_item: dict = {
            "articleId": article_id,
            "userId": user_id,
            "title": article["title"],
            "html": article["html"],
            "creation_timestamp": creation_timestamp,
            "further_reading": further_reading,
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


def validate_input(state: WorkflowState) -> None:
    if not state.userId:
        logger.error("article-handler: missing userId in event")
        raise ValueError("userId is required")
    if not state.articleId:
        logger.error("article-handler: missing articleId in event")
        raise ValueError("articleId is required")
    if not state.articleTopic:
        logger.error("article-handler: missing articleTopic in event")
        raise ValueError("articleTopic is required")


def handler(event, context):
    state = WorkflowState.from_event(event)
    validate_input(state)

    api_key = load_api_key()
    os.environ["OPENAI_API_KEY"] = api_key

    s3 = boto3.client("s3", region_name=AWS_REGION)
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)

    base_instructions = load_instructions(s3, os.environ["INPUT_BUCKET"])
    user_tastes = load_user_tastes(s3, os.environ["INPUT_BUCKET"], state.userId)

    if not state.tavilyResults:
        logger.warning("article-handler: tavilyResults absent — proceeding without further reading sources")
    further_reading = build_further_reading(state.tavilyResults) if state.tavilyResults else "[]"

    try:
        if state.followUpArticleId:
            follow_up_instructions = load_follow_up_instructions(s3, os.environ["INPUT_BUCKET"])
            combined_instructions = base_instructions + "\n" + follow_up_instructions
            original_html = load_original_article_html(ddb, state.followUpArticleId)
            article = generate_follow_up_article(
                state.articleId, original_html, state.extraContent or "", user_tastes, combined_instructions, state.tavilyResults
            )
        else:
            article = generate_article(state.articleId, state.articleTopic, base_instructions, user_tastes, state.tavilyResults)
    except Exception as e:
        logger.error("article-handler: article generation failed: %s", e)
        raise

    if state.followUpArticleId:
        save_article(ddb, state.articleId, state.userId, article, now_utc_iso(),
                     further_reading=further_reading, source_article_id=state.followUpArticleId)
    else:
        save_article(ddb, state.articleId, state.userId, article, now_utc_iso(), further_reading=further_reading)

    return WorkflowState(
        userId=state.userId,
        articleId=state.articleId,
        articleTopic=state.articleTopic,
        articleTitle=article["title"],
    ).to_dict()
