import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ENV = {
    "SECRET_NAME": "pulseq/openai-api-key",
    "IFTTT_SECRET_NAME": "pulseq/ifttt-key",
    "INPUT_BUCKET": "pulseq-inputs",
    "ARTICLES_TABLE": "pulseq-articles",
    "TOPICS_TABLE": "pulseq-topics",
    "WEB_BASE_URL": "https://test-web.execute-api.eu-west-1.amazonaws.com",
}

SECRETS = {
    "pulseq/openai-api-key": "sk-test",
    "pulseq/ifttt-key": "ifttt-test-key",
}

SAMPLE_TOPICS = [{"title": "N+1 Queries", "description": "Detection patterns."}]

SAMPLE_ARTICLE = {
    "id": "abc12",
    "html": (
        "<style>:root { --accent: #0d9488; }</style>\n"
        '<div class="header-card"><h1>How Load Balancers Work</h1></div>\n'
        '<div class="section"><p>Content.</p></div>'
    ),
    "title": "How Load Balancers Work",
    "accent": "#0d9488",
}


def _make_sm_client():
    def _get_secret_value(SecretId):
        if SecretId not in SECRETS:
            raise Exception(f"unexpected secret: {SecretId}")
        return {"SecretString": SECRETS[SecretId]}

    sm = MagicMock()
    sm.get_secret_value.side_effect = _get_secret_value
    return sm


def _make_s3_client():
    """Return a mock S3 client that writes instructions.md to the dest path."""
    def _download_file(bucket, key, dest):
        if key == "shared/instructions.md":
            Path(dest).write_text("# Instructions")

    s3 = MagicMock()
    s3.download_file.side_effect = _download_file
    return s3


def _make_topics_table(topics=None):
    """Return a mock DDB Table for topics. topics=None means missing item."""
    table = MagicMock()
    if topics is None:
        table.get_item.return_value = {}
    else:
        table.get_item.return_value = {"Item": {"userId": "user1", "topics": topics}}
    return table


def _make_articles_table():
    table = MagicMock()
    return table


def _make_ddb_resource(topics_table=None, articles_table=None):
    """Return a mock boto3 DynamoDB resource. Table() returns topics_table or
    articles_table based on call order (topics first, articles second)."""
    tt = topics_table or _make_topics_table(SAMPLE_TOPICS)
    at = articles_table or _make_articles_table()
    ddb = MagicMock()
    ddb.Table.side_effect = lambda name: tt if name == "pulseq-topics" else at
    return ddb, tt, at


def _fake_run(base_dir, topic):
    return SAMPLE_ARTICLE.copy()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLambdaHandler:
    def setup_method(self):
        import writer.lambda_handler as lh
        lh._api_key = None
        lh._ifttt_key = None

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_happy_path(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, topics_table, articles_table = _make_ddb_resource()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["url"] == "https://test-web.execute-api.eu-west-1.amazonaws.com/abc12"

        articles_table.put_item.assert_called_once()
        item = articles_table.put_item.call_args.kwargs["Item"]
        assert item["userid"] == "user1"
        assert item["id"] == "abc12"
        assert item["title"] == "How Load Balancers Work"
        assert item["accent"] == "#0d9488"
        assert item["html"] == SAMPLE_ARTICLE["html"]
        assert isinstance(item["creation_timestamp"], str)

        # warm-up calls the article API endpoint, notification uses the React app URL
        assert mock_urlopen.call_count == 2
        warmup_url = mock_urlopen.call_args_list[0].args[0]
        assert warmup_url == "https://test-web.execute-api.eu-west-1.amazonaws.com/api/article/abc12"

        # chosen topic is removed after successful put_item
        topics_table.update_item.assert_called_once_with(
            Key={"userId": "user1"},
            UpdateExpression="SET topics = :topics",
            ConditionExpression="topics = :orig",
            ExpressionAttributeValues={":topics": [], ":orig": SAMPLE_TOPICS},
        )

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_run_receives_topic(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        """Lambda picks a topic from DDB and passes it to run()."""
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        handler({"userId": "user1"}, None)

        _, kwargs = mock_run.call_args
        assert kwargs["topic"] == "N+1 Queries — Detection patterns."
        assert "history" not in kwargs

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    def test_empty_topics_list_fails(self, mock_boto_client, mock_boto_resource):
        """DDB returns empty topics list → 500."""
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, _, _ = _make_ddb_resource(topics_table=_make_topics_table([]))
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to download inputs" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    def test_missing_topics_item_fails(self, mock_boto_client, mock_boto_resource):
        """DDB returns no item for user → 500."""
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, _, _ = _make_ddb_resource(topics_table=_make_topics_table(None))
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to download inputs" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_notification_failure_is_nonfatal(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb
        mock_urlopen.side_effect = Exception("IFTTT unreachable")

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_warmup_failure_is_nonfatal(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        """Warm-up failure does not block notification or success response."""
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb
        mock_urlopen.side_effect = [Exception("warm-up timeout"), None]

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200
        assert mock_urlopen.call_count == 2

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_s3_download_failure(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        from botocore.exceptions import ClientError
        sm = _make_sm_client()
        s3 = _make_s3_client()
        s3.download_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "download_file"
        )
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to download inputs" in json.loads(result["body"])["error"]
        mock_run.assert_not_called()

    @patch.dict(os.environ, ENV)
    def test_missing_user_id_returns_400(self):
        with patch("writer.lambda_handler.logger.error") as error_spy:
            from writer.lambda_handler import handler
            result = handler({}, None)
        assert result["statusCode"] == 400
        assert "userId" in json.loads(result["body"])["error"]
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.client")
    def test_secrets_manager_failure(self, mock_boto_client):
        sm = MagicMock()
        sm.get_secret_value.side_effect = Exception("AccessDenied")
        mock_boto_client.return_value = sm

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to retrieve secret" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_api_key_cached_across_calls(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        handler({"userId": "user1"}, None)
        handler({"userId": "user1"}, None)

        # Each secret fetched only once despite two handler invocations
        assert sm.get_secret_value.call_count == 2  # one per secret, not per invocation

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_ddb_put_failure(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        from botocore.exceptions import ClientError
        sm = _make_sm_client()
        s3 = _make_s3_client()
        articles_table = _make_articles_table()
        articles_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Throttled"}},
            "put_item",
        )
        ddb, _, _ = _make_ddb_resource(articles_table=articles_table)
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "Failed to save article" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=RuntimeError("writer failed"))
    def test_writer_run_failure(self, mock_run, mock_boto_client, mock_boto_resource):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, topics_table, _ = _make_ddb_resource()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        from writer.lambda_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 500
        assert "writer.run() failed" in json.loads(result["body"])["error"]
        topics_table.update_item.assert_not_called()

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.resource")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_topic_consume_fail_open(self, mock_run, mock_boto_client, mock_boto_resource, mock_urlopen):
        """update_item failure is non-fatal: logger.warning called, handler still returns 200."""
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, topics_table, _ = _make_ddb_resource()
        topics_table.update_item.side_effect = Exception("ConditionalCheckFailedException")
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_boto_resource.return_value = ddb

        with patch("writer.lambda_handler.logger.warning") as warn_spy:
            from writer.lambda_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result["statusCode"] == 200
        warn_spy.assert_called_once()
