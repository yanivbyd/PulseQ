import json
import logging
import os
import urllib.request

import boto3

try:
    from handler_utils import AWS_REGION
    from workflow_state import WorkflowState
except ImportError:
    from writer.handler_utils import AWS_REGION  # type: ignore[no-redef]
    from writer.workflow_state import WorkflowState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
PAYLOAD_WARN_BYTES = 200 * 1024  # 200 KB


def get_tavily_api_key() -> str:
    secret_name = os.environ["TAVILY_SECRET_NAME"]
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=secret_name)
    return response["SecretString"]


def call_tavily(api_key: str, article_topic: str) -> dict:
    payload = {
        "query": f"Blog posts related to {article_topic}",
        "search_depth": "advanced",
        "topic": "general",
        "max_results": 5,
        "include_raw_content": False,
        "include_images": True,
        "include_image_descriptions": True,
        "chunks_per_source": 5,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TAVILY_SEARCH_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def handler(event, context):
    state = WorkflowState.from_event(event)

    if not state.articleTopic:
        logger.error("tavily-handler: missing articleTopic in event")
        raise ValueError("articleTopic is required")

    try:
        api_key = get_tavily_api_key()
    except Exception as e:
        logger.error("tavily-handler: failed to retrieve Tavily API key: %s", e)
        raise

    try:
        tavily_results = call_tavily(api_key, state.articleTopic)
    except Exception as e:
        logger.error("tavily-handler: Tavily search failed: %s", e)
        raise

    payload_bytes = len(json.dumps(tavily_results).encode("utf-8"))
    logger.info("tavily-handler: tavilyResults payload size: %d bytes", payload_bytes)
    if payload_bytes > PAYLOAD_WARN_BYTES:
        logger.warning(
            "tavily-handler: tavilyResults payload size %d bytes exceeds 200 KB", payload_bytes
        )

    return WorkflowState(
        userId=state.userId,
        articleId=state.articleId,
        articleTopic=state.articleTopic,
        tavilyResults=tavily_results,
        followUpArticleId=state.followUpArticleId,
        extraContent=state.extraContent,
    ).to_dict()
