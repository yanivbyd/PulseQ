import json
import logging
import os
import urllib.request

import boto3

# In Lambda the bundle root contains sibling modules.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from handler_utils import AWS_REGION
    from workflow_state import WorkflowState
except ImportError:
    from writer.handler_utils import AWS_REGION  # type: ignore[no-redef]
    from writer.workflow_state import WorkflowState  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

_ifttt_key: str | None = None


def _get_ifttt_key() -> str:
    global _ifttt_key
    if _ifttt_key is None:
        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        response = client.get_secret_value(SecretId=os.environ["IFTTT_SECRET_NAME"])
        _ifttt_key = response["SecretString"]
    return _ifttt_key


def warm_up_cache(url: str) -> None:
    try:
        urllib.request.urlopen(url, timeout=10)
    except Exception as e:
        logger.warning("notification-handler: warm-up request failed: %s", e)


def send_ifttt_notification(article_url: str, article_title: str) -> None:
    try:
        key = _get_ifttt_key()
        endpoint = f"https://maker.ifttt.com/trigger/PulseQ/with/key/{key}"
        data = json.dumps({"value1": article_url, "value2": article_title}).encode()
        req = urllib.request.Request(
            endpoint, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)
    except Exception as e:
        logger.error("notification-handler: failed to send IFTTT notification: %s", e)
        raise


def handler(event, context):
    state = WorkflowState.from_event(event)

    if not state.articleId or not state.userId or not state.articleTitle:
        logger.error("notification-handler: missing articleId, userId, or articleTitle in event")
        raise ValueError("articleId, userId, and articleTitle are required")

    web_base = os.environ["WEB_BASE_URL"]
    warm_up_cache(f"{web_base}/api/article/{state.articleId}")
    send_ifttt_notification(f"{web_base}/{state.articleId}", state.articleTitle)

    return {}
