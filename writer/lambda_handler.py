import json
import logging
import os
import random
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import boto3

# In Lambda the bundle root contains writer.py as a sibling module.
# In tests writer/ is a package, so fall back to the submodule import.
try:
    from writer import run  # Lambda environment: writer.py at bundle root
except ImportError:
    from writer.writer import run  # type: ignore[no-redef]  # Test environment

logger = logging.getLogger(__name__)

# Module-level caches (populated on cold start)
_api_key: str | None = None
_ifttt_key: str | None = None


def _get_api_key() -> str:
    global _api_key
    if _api_key is None:
        client = boto3.client("secretsmanager", region_name="eu-west-1")
        response = client.get_secret_value(SecretId=os.environ["SECRET_NAME"])
        _api_key = response["SecretString"]
    return _api_key


def _get_ifttt_key() -> str:
    global _ifttt_key
    if _ifttt_key is None:
        client = boto3.client("secretsmanager", region_name="eu-west-1")
        response = client.get_secret_value(SecretId=os.environ["IFTTT_SECRET_NAME"])
        _ifttt_key = response["SecretString"]
    return _ifttt_key


def _load_inputs(
    s3_client, bucket: str, topics_table, tmp_inputs: Path, user_id: str
) -> tuple[str, dict, list]:
    s3_client.download_file(bucket, "shared/instructions.md", str(tmp_inputs / "instructions.md"))

    resp = topics_table.get_item(Key={"userId": user_id})
    topics: list[dict[str, str]] = resp.get("Item", {}).get("topics", [])
    if not topics:
        raise ValueError("no topics found for user")
    chosen = random.choice(topics)
    return f"{chosen['title']} — {chosen['description']}", chosen, topics


def _warm_up(url: str) -> None:
    try:
        urllib.request.urlopen(url, timeout=10)
    except Exception as e:
        print(f"Warning: warm-up request failed: {e}")


def _send_notification(url: str, title: str) -> None:
    key = _get_ifttt_key()
    endpoint = f"https://maker.ifttt.com/trigger/PulseQ/with/key/{key}"
    data = json.dumps({"value1": url, "value2": title}).encode()
    req = urllib.request.Request(
        endpoint, data=data, headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req)


def handler(event, context):
    user_id = event.get("userId")
    if not user_id:
        logger.error("writer: missing userId in event")
        return {"statusCode": 400, "body": json.dumps({"error": "userId is required"})}

    input_bucket = os.environ["INPUT_BUCKET"]
    table_name = os.environ["ARTICLES_TABLE"]

    try:
        api_key = _get_api_key()
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to retrieve secret: {e}"})}

    os.environ["OPENAI_API_KEY"] = api_key

    s3 = boto3.client("s3", region_name="eu-west-1")
    topics_table = boto3.resource("dynamodb", region_name="eu-west-1").Table(os.environ["TOPICS_TABLE"])

    with tempfile.TemporaryDirectory() as tmp:
        tmp_inputs = Path(tmp) / "inputs"
        tmp_inputs.mkdir()

        try:
            topic, chosen, topics = _load_inputs(s3, input_bucket, topics_table, tmp_inputs, user_id)
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": f"Failed to download inputs: {e}"})}

        try:
            article = run(base_dir=Path(tmp), topic=topic)
        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"error": f"writer.run() failed: {e}"})}

    creation_timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    try:
        table = boto3.resource("dynamodb", region_name="eu-west-1").Table(table_name)
        table.put_item(Item={
            "userid": user_id,
            "creation_timestamp": creation_timestamp,
            "id": article["id"],
            "title": article["title"],
            "accent": article["accent"],
            "html": article["html"],
        })
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to save article: {e}"})}

    remaining = [t for t in topics if t["title"] != chosen["title"]]
    try:
        topics_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET topics = :topics",
            ConditionExpression="topics = :orig",
            ExpressionAttributeValues={":topics": remaining, ":orig": topics},
        )
    except Exception as e:
        logger.warning("writer: failed to remove consumed topic from DDB; topic may be reused: %s", e)

    article_url = f"{os.environ['WEB_BASE_URL']}/{article['id']}"
    warmup_url = f"{os.environ['WEB_BASE_URL']}/api/article/{article['id']}"

    _warm_up(warmup_url)

    try:
        _send_notification(article_url, article["title"])
    except Exception as e:
        # Non-fatal — article was written successfully, notification is best-effort
        print(f"Warning: failed to send notification: {e}")

    return {"statusCode": 200, "body": json.dumps({"url": article_url})}
