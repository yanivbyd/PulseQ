import json
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest


ENV = {
    "SECRET_NAME": "pulseq/openai-api-key",
    "INPUT_BUCKET": "pulseq-inputs",
    "EVENTS_BUCKET": "pulseq-events",
    "TOPICS_TABLE": "pulseq-topics",
}

SAMPLE_INSTRUCTIONS = "You are a scout."
SAMPLE_USER_TASTES = "Prefer backend and infra."
SAMPLE_TOPICS = [{"title": "How Kafka Works", "description": "Deep dive."}]
UPDATED_TOPICS = [{"title": f"Topic {i}", "description": f"Desc {i}."} for i in range(10)]
FEEDBACK_EVENT = {"articleId": "abc12", "articleTitle": "How Kafka Works", "reaction": "like"}


def _body(data: bytes):
    return {"Body": BytesIO(data)}


def _make_s3(
    feedback_events=None,
    get_object_raises=None,
    list_raises=None,
):
    """Build a mock S3 client (instructions, user_tastes, feedback events only)."""
    events = feedback_events or []

    def _get_object(Bucket, Key):
        if get_object_raises and Key in get_object_raises:
            raise get_object_raises[Key]
        if Key == "shared/scout_instructions.md":
            return _body(SAMPLE_INSTRUCTIONS.encode())
        if Key == "user1/user_tastes.md":
            return _body(SAMPLE_USER_TASTES.encode())
        # feedback event key: "<userId>/<idx>.json"
        idx = int(Key.split("/")[1].replace(".json", ""))
        return _body(json.dumps(events[idx]).encode())

    # Keys in ascending order; handler will sort descending
    list_contents = [{"Key": f"user1/{i}.json"} for i in range(len(events))]

    s3 = MagicMock()
    s3.get_object.side_effect = _get_object
    if list_raises:
        s3.list_objects_v2.side_effect = list_raises
    else:
        s3.list_objects_v2.return_value = {"Contents": list_contents}
    return s3


def _make_sm():
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": "sk-test"}
    return sm


def _make_topics_table(topics=SAMPLE_TOPICS, get_raises=None, put_raises=None):
    """Build a mock DynamoDB Table for topics."""
    table = MagicMock()
    if get_raises:
        table.get_item.side_effect = get_raises
    else:
        item = {"userId": "user1", "topics": topics} if topics is not None else None
        table.get_item.return_value = {"Item": item} if item is not None else {}
    if put_raises:
        table.put_item.side_effect = put_raises
    return table


def _make_ddb_resource(topics_table):
    ddb = MagicMock()
    ddb.Table.return_value = topics_table
    return ddb


# ── fixtures ──────────────────────────────────────────────────────────────────

class TestScoutLambdaHandler:
    def setup_method(self):
        import scout.lambda_handler as lh
        lh._api_key = None

    # ── happy path ────────────────────────────────────────────────────────────

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_happy_path(self, mock_run, mock_boto_client, mock_boto_resource):
        sm, s3 = _make_sm(), _make_s3()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table())

        from scout.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200
        assert json.loads(result["body"]) == {"userId": "user1", "total": 10}

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_run_called_with_ddb_loaded_topics(self, mock_run, mock_boto_client, mock_boto_resource):
        sm, s3 = _make_sm(), _make_s3(feedback_events=[FEEDBACK_EVENT])
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table())

        from scout.lambda_handler import handler
        handler({"userId": "user1"}, None)

        args = mock_run.call_args.args
        assert args[0] == SAMPLE_INSTRUCTIONS
        assert args[1] == SAMPLE_USER_TASTES
        assert args[2] == SAMPLE_TOPICS
        assert args[3] == [FEEDBACK_EVENT]
        assert mock_run.call_args.kwargs["api_key"] == "sk-test"

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_topics_saved_to_ddb(self, mock_run, mock_boto_client, mock_boto_resource):
        sm, s3 = _make_sm(), _make_s3()
        topics_table = _make_topics_table()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(topics_table)

        from scout.lambda_handler import handler
        handler({"userId": "user1"}, None)

        topics_table.put_item.assert_called_once_with(
            Item={"userId": "user1", "topics": UPDATED_TOPICS}
        )

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_missing_topics_row_treated_as_empty(self, mock_run, mock_boto_client, mock_boto_resource):
        """Missing DDB item → scout generates fresh topics (run() called with [])."""
        sm, s3 = _make_sm(), _make_s3()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table(topics=None))

        from scout.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200
        assert mock_run.call_args.args[2] == []

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_feedback_events_sorted_descending(self, mock_run, mock_boto_client, mock_boto_resource):
        """Events are passed to run() in descending key order (newest first)."""
        event_a = {**FEEDBACK_EVENT, "articleTitle": "Article A"}
        event_b = {**FEEDBACK_EVENT, "articleTitle": "Article B"}
        sm, s3 = _make_sm(), _make_s3(feedback_events=[event_a, event_b])
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table())

        from scout.lambda_handler import handler
        handler({"userId": "user1"}, None)

        assert mock_run.call_args.args[3] == [event_b, event_a]

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_api_key_cached_across_calls(self, mock_run, mock_boto_client, mock_boto_resource):
        sm, s3 = _make_sm(), _make_s3()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table())

        from scout.lambda_handler import handler
        handler({"userId": "user1"}, None)
        handler({"userId": "user1"}, None)

        sm.get_secret_value.assert_called_once()

    # ── error paths ───────────────────────────────────────────────────────────

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.client")
    def test_missing_user_id_returns_400(self, mock_boto_client):
        with patch("scout.lambda_handler.logger.error") as error_spy:
            from scout.lambda_handler import handler
            result = handler({}, None)
        assert result["statusCode"] == 400
        assert "userId" in json.loads(result["body"])["error"]
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.client")
    def test_secrets_manager_failure_returns_500(self, mock_boto_client):
        sm = MagicMock()
        sm.get_secret_value.side_effect = Exception("AccessDenied")
        mock_boto_client.return_value = sm

        with patch("scout.lambda_handler.logger.error") as error_spy:
            from scout.lambda_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to retrieve secret" in json.loads(result["body"])["error"]
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_topics_ddb_failure_is_failopen(self, mock_run, mock_boto_client, mock_boto_resource):
        """DDB GetItem failure → proceed with empty topics, warn."""
        sm, s3 = _make_sm(), _make_s3()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(
            _make_topics_table(get_raises=Exception("DDB unavailable"))
        )

        with patch("scout.lambda_handler.logger.warning") as warn_spy:
            from scout.lambda_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200
        warn_spy.assert_called_once()
        assert mock_run.call_args.args[2] == []

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    def test_instructions_load_failure_returns_500(self, mock_boto_client, mock_boto_resource):
        sm = _make_sm()
        s3 = _make_s3(get_object_raises={"shared/scout_instructions.md": Exception("NoSuchKey")})
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table())

        with patch("scout.lambda_handler.logger.error") as error_spy:
            from scout.lambda_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to load instructions" in json.loads(result["body"])["error"]
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_feedback_events_failure_is_failopen(self, mock_run, mock_boto_client, mock_boto_resource):
        sm, s3 = _make_sm(), _make_s3(list_raises=Exception("S3 listing error"))
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table())

        with patch("scout.lambda_handler.logger.warning") as warn_spy:
            from scout.lambda_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200
        warn_spy.assert_called_once()
        assert mock_run.call_args.args[3] == []

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", side_effect=Exception("OpenAI down"))
    def test_run_failure_returns_500(self, mock_run, mock_boto_client, mock_boto_resource):
        sm, s3 = _make_sm(), _make_s3()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(_make_topics_table())

        with patch("scout.lambda_handler.logger.error") as error_spy:
            from scout.lambda_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "scout.run() failed" in json.loads(result["body"])["error"]
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("scout.lambda_handler.boto3.resource")
    @patch("scout.lambda_handler.boto3.client")
    @patch("scout.lambda_handler.run", return_value=UPDATED_TOPICS)
    def test_save_topics_failure_returns_500(self, mock_run, mock_boto_client, mock_boto_resource):
        sm, s3 = _make_sm(), _make_s3()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = _make_ddb_resource(
            _make_topics_table(put_raises=Exception("DDB put failed"))
        )

        with patch("scout.lambda_handler.logger.error") as error_spy:
            from scout.lambda_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to save topics" in json.loads(result["body"])["error"]
        error_spy.assert_called_once()
