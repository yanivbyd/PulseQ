import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)

try:
    from scout import run  # Lambda environment: scout.py at bundle root
except ImportError:
    from scout.scout import run  # type: ignore[no-redef]  # Test environment

# Module-level cache (populated on cold start)
_api_key: str | None = None


def _get_api_key() -> str:
    global _api_key
    if _api_key is None:
        client = boto3.client("secretsmanager", region_name="eu-west-1")
        response = client.get_secret_value(SecretId=os.environ["SECRET_NAME"])
        _api_key = response["SecretString"]
    return _api_key


def handler(event, context):
    user_id = event.get("userId")
    if not user_id:
        logger.error("scout: missing userId in event")
        return {"statusCode": 400, "body": json.dumps({"error": "userId is required"})}

    input_bucket = os.environ["INPUT_BUCKET"]
    events_bucket = os.environ["EVENTS_BUCKET"]

    try:
        api_key = _get_api_key()
    except Exception as e:
        logger.error("scout: failed to retrieve secret: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to retrieve secret: {e}"})}

    s3 = boto3.client("s3", region_name="eu-west-1")

    try:
        topics_obj = s3.get_object(Bucket=input_bucket, Key=f"{user_id}/topics.json")
        topics = json.loads(topics_obj["Body"].read()).get("topics", [])
    except Exception as e:
        logger.error("scout: failed to load topics: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to load topics: {e}"})}

    try:
        instructions = s3.get_object(
            Bucket=input_bucket, Key="shared/scout_instructions.md"
        )["Body"].read().decode()
        user_tastes = s3.get_object(
            Bucket=input_bucket, Key=f"{user_id}/user_tastes.md"
        )["Body"].read().decode()
    except Exception as e:
        logger.error("scout: failed to load instructions: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to load instructions: {e}"})}

    try:
        feedback_events = []
        response = s3.list_objects_v2(Bucket=events_bucket, Prefix=f"{user_id}/")
        objects = sorted(response.get("Contents", []), key=lambda o: o["Key"], reverse=True)
        for obj in objects:
            data = s3.get_object(Bucket=events_bucket, Key=obj["Key"])
            feedback_events.append(json.loads(data["Body"].read()))
    except Exception as e:
        logger.warning("scout: failed to load feedback events, proceeding without: %s", e)
        feedback_events = []

    try:
        updated_topics = run(instructions, user_tastes, topics, feedback_events, api_key=api_key)
    except Exception as e:
        logger.error("scout: run() failed: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": f"scout.run() failed: {e}"})}

    try:
        s3.put_object(
            Bucket=input_bucket,
            Key=f"{user_id}/topics.json",
            Body=json.dumps({"topics": updated_topics}),
            ContentType="application/json",
        )
    except Exception as e:
        logger.error("scout: failed to save topics: %s", e)
        return {"statusCode": 500, "body": json.dumps({"error": f"Failed to save topics: {e}"})}

    logger.info("scout: updated topics count=%d for userId=%s", len(updated_topics), user_id)
    return {"statusCode": 200, "body": json.dumps({"userId": user_id, "total": len(updated_topics)})}
