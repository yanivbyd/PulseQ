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
    "OUTPUT_BUCKET": "pulseq",
    "WEB_BASE_URL": "https://test-web.execute-api.eu-west-1.amazonaws.com",
}

SECRETS = {
    "pulseq/openai-api-key": "sk-test",
    "pulseq/ifttt-key": "ifttt-test-key",
}

SAMPLE_TOPICS = {
    "topics": [{"title": "N+1 Queries", "description": "Detection patterns."}]
}


def _make_sm_client():
    def _get_secret_value(SecretId):
        if SecretId not in SECRETS:
            raise Exception(f"unexpected secret: {SecretId}")
        return {"SecretString": SECRETS[SecretId]}

    sm = MagicMock()
    sm.get_secret_value.side_effect = _get_secret_value
    return sm


def _make_s3_client(topics=None):
    """Return a mock S3 client that writes JSON/md content to the dest path on download."""
    topics_content = json.dumps(topics if topics is not None else SAMPLE_TOPICS)

    def _download_file(bucket, key, dest):
        if key == "inputs/topics.json":
            Path(dest).write_text(topics_content)
        elif key == "inputs/instructions.md":
            Path(dest).write_text("# Instructions")

    s3 = MagicMock()
    s3.download_file.side_effect = _download_file
    return s3


def _fake_run(base_dir, docs_dir, topic):
    """Simulate writer.run() creating one HTML file."""
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "abc12.html").write_text("<html><head><title>How Load Balancers Work</title></head></html>")


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
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_happy_path(self, mock_run, mock_boto_client, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["url"] == "https://test-web.execute-api.eu-west-1.amazonaws.com/abc12"
        s3.upload_file.assert_called_once()
        _, upload_args, upload_kwargs = s3.upload_file.mock_calls[0]
        assert upload_kwargs["ExtraArgs"] == {"ContentType": "text/html"}
        # warm-up call + notification call
        assert mock_urlopen.call_count == 2

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_run_receives_topic(self, mock_run, mock_boto_client, mock_urlopen):
        """Lambda picks a topic from topics.json and passes it to run()."""
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        handler({}, None)

        _, kwargs = mock_run.call_args
        assert kwargs["topic"] == "N+1 Queries — Detection patterns."
        assert "history" not in kwargs

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.client")
    def test_empty_topics_list_fails(self, mock_boto_client):
        """topics.json with an empty array returns 500."""
        sm = _make_sm_client()
        s3 = _make_s3_client(topics={"topics": []})
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "Failed to download inputs" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_notification_failure_is_nonfatal(self, mock_run, mock_boto_client, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        mock_urlopen.side_effect = Exception("IFTTT unreachable")

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 200

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_warmup_failure_is_nonfatal(self, mock_run, mock_boto_client, mock_urlopen):
        """Warm-up failure does not block notification or success response."""
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3
        # First call (warm-up) fails; second call (notification) succeeds
        mock_urlopen.side_effect = [Exception("warm-up timeout"), None]

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 200
        assert mock_urlopen.call_count == 2

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_s3_download_failure(self, mock_run, mock_boto_client, mock_urlopen):
        from botocore.exceptions import ClientError
        sm = _make_sm_client()
        s3 = _make_s3_client()
        s3.download_file.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "download_file"
        )
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "Failed to download inputs" in json.loads(result["body"])["error"]
        mock_run.assert_not_called()

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.client")
    def test_secrets_manager_failure(self, mock_boto_client):
        sm = MagicMock()
        sm.get_secret_value.side_effect = Exception("AccessDenied")
        mock_boto_client.return_value = sm

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "Failed to retrieve secret" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_api_key_cached_across_calls(self, mock_run, mock_boto_client, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        handler({}, None)
        handler({}, None)

        # Each secret fetched only once despite two handler invocations
        assert sm.get_secret_value.call_count == 2  # one per secret, not per invocation

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_s3_upload_failure(self, mock_run, mock_boto_client, mock_urlopen):
        from botocore.exceptions import ClientError
        sm = _make_sm_client()
        s3 = _make_s3_client()
        s3.upload_file.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Forbidden"}}, "upload_file"
        )
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "Failed to upload output" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=RuntimeError("writer failed"))
    def test_writer_run_failure(self, mock_run, mock_boto_client, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "writer.run() failed" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.urllib.request.urlopen")
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run")  # does nothing — produces no HTML
    def test_no_html_produced(self, mock_run, mock_boto_client, mock_urlopen):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "No HTML output produced" in json.loads(result["body"])["error"]
