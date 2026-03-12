import json
import logging
import os

import boto3
import openai
from boto3.dynamodb.conditions import Key

# In Lambda the bundle root contains sibling modules.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from writer import generate_quiz  # Lambda environment
    from handler_utils import AWS_REGION, get_openai_api_key, s3_get_text
except ImportError:
    from writer.writer import generate_quiz  # type: ignore[no-redef]  # Test environment
    from writer.handler_utils import AWS_REGION, get_openai_api_key, s3_get_text  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


def handler(event, context):
    article_id = event.get("articleId")
    user_id = event.get("userId")
    if not article_id or not user_id:
        logger.error("quiz-handler: missing articleId or userId in event")
        raise ValueError("articleId and userId are required")

    try:
        api_key = get_openai_api_key()
    except Exception as e:
        logger.error("quiz-handler: failed to retrieve secret: %s", e)
        raise

    s3 = boto3.client("s3", region_name=AWS_REGION)
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    articles_table = ddb.Table(os.environ["ARTICLES_TABLE"])

    try:
        result = articles_table.query(
            IndexName="ById",
            KeyConditionExpression=Key("id").eq(article_id),
            Limit=1,
        )
        items = result.get("Items", [])
        if not items:
            raise ValueError(f"article not found: {article_id}")
        item = items[0]
        html = item["html"]
        userid = item["userid"]
        creation_timestamp = item["creation_timestamp"]
    except Exception as e:
        logger.error("quiz-handler: failed to load article from DDB: %s", e)
        raise

    try:
        shared_quiz = s3_get_text(
            s3, os.environ["INPUT_BUCKET"], "shared/quiz_generation_instructions.txt"
        )
        user_quiz = s3_get_text(
            s3, os.environ["INPUT_BUCKET"], f"{user_id}/quiz_user_tastes.txt"
        )
        quiz_prompt = shared_quiz + user_quiz
    except Exception as e:
        logger.error("quiz-handler: failed to load quiz prompt from S3: %s", e)
        raise

    client = openai.OpenAI(api_key=api_key)
    quiz = generate_quiz(client, html, quiz_prompt)

    try:
        articles_table.update_item(
            Key={"userid": userid, "creation_timestamp": creation_timestamp},
            UpdateExpression="SET quiz = :quiz",
            ExpressionAttributeValues={":quiz": json.dumps(quiz)},
        )
    except Exception as e:
        logger.error("quiz-handler: failed to update article quiz in DDB: %s", e)
        raise

    return {"articleId": article_id, "userId": user_id}
