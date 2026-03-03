import json
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

USER_ID = "user1"

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


def _load_inputs(s3_client, bucket: str, tmp_inputs: Path) -> str:
    for key in ("instructions.md", "topics.json"):
        s3_client.download_file(bucket, f"inputs/{key}", str(tmp_inputs / key))

    topics_data = json.loads((tmp_inputs / "topics.json").read_text())
    topics = topics_data.get("topics", [])
    if not topics:
        raise ValueError("topics.json contains no topics")
    chosen = random.choice(topics)
    return f"{chosen['title']} — {chosen['description']}"


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
    input_bucket = os.environ["INPUT_BUCKET"]
    table_name = os.environ["ARTICLES_TABLE"]

    try:
        api_key = _get_api_key()
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to retrieve secret: {e}"})}

    os.environ["OPENAI_API_KEY"] = api_key

    s3 = boto3.client("s3", region_name="eu-west-1")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_inputs = Path(tmp) / "inputs"
        tmp_inputs.mkdir()

        try:
            topic = _load_inputs(s3, input_bucket, tmp_inputs)
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
            "userid": USER_ID,
            "creation_timestamp": creation_timestamp,
            "id": article["id"],
            "title": article["title"],
            "accent": article["accent"],
            "html": article["html"],
        })
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to save article: {e}"})}

    url = f"{os.environ['WEB_BASE_URL']}/{article['id']}"

    _warm_up(url)

    try:
        _send_notification(url, article["title"])
    except Exception as e:
        # Non-fatal — article was written successfully, notification is best-effort
        print(f"Warning: failed to send notification: {e}")

    return {"statusCode": 200, "body": json.dumps({"url": url})}
