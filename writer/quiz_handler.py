import json
import logging
import os

import boto3
import openai

# In Lambda the bundle root contains sibling modules.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from writer import generate_quiz  # Lambda environment
    from handler_utils import AWS_REGION, get_openai_api_key, s3_get_text
    from workflow_state import WorkflowState
except ImportError:
    from writer.writer import generate_quiz  # type: ignore[no-redef]  # Test environment
    from writer.handler_utils import AWS_REGION, get_openai_api_key, s3_get_text  # type: ignore[no-redef]
    from writer.workflow_state import WorkflowState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def load_api_key() -> str:
    try:
        return get_openai_api_key()
    except Exception as e:
        logger.error("quiz-handler: failed to retrieve secret: %s", e)
        raise


def load_article_html(articles_table, article_id: str) -> str:
    try:
        result = articles_table.get_item(Key={"articleId": article_id})
        item = result.get("Item")
        if not item:
            raise ValueError(f"article not found: {article_id}")
        return item["html"]
    except Exception as e:
        logger.error("quiz-handler: failed to load article from DDB: %s", e)
        raise


def load_quiz_prompt(s3, bucket: str, user_id: str) -> str:
    try:
        shared = s3_get_text(s3, bucket, "shared/quiz_generation_instructions.txt")
        user = s3_get_text(s3, bucket, f"{user_id}/quiz_user_tastes.txt")
        return shared + user
    except Exception as e:
        logger.error("quiz-handler: failed to load quiz prompt from S3: %s", e)
        raise


def save_quiz(articles_table, article_id: str, quiz: list) -> None:
    try:
        articles_table.update_item(
            Key={"articleId": article_id},
            UpdateExpression="SET quiz = :quiz",
            ExpressionAttributeValues={":quiz": json.dumps(quiz)},
        )
    except Exception as e:
        logger.error("quiz-handler: failed to update article quiz in DDB: %s", e)
        raise


def handler(event, context):
    state = WorkflowState.from_event(event)

    if not state.articleId or not state.userId:
        logger.error("quiz-handler: missing articleId or userId in event")
        raise ValueError("articleId and userId are required")

    api_key = load_api_key()

    s3 = boto3.client("s3", region_name=AWS_REGION)
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    articles_table = ddb.Table(os.environ["ARTICLES_TABLE"])

    html = load_article_html(articles_table, state.articleId)
    quiz_prompt = load_quiz_prompt(s3, os.environ["INPUT_BUCKET"], state.userId)

    quiz = generate_quiz(openai.OpenAI(api_key=api_key), html, quiz_prompt)
    save_quiz(articles_table, state.articleId, quiz)

    return WorkflowState(
        userId=state.userId,
        articleId=state.articleId,
        articleTitle=state.articleTitle,
    ).to_dict()
