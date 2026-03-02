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
    "INPUT_BUCKET": "pulseq-inputs",
    "OUTPUT_BUCKET": "pulseq",
}


def _make_sm_client(secret_value="sk-test"):
    def _get_secret_value(SecretId):
        if SecretId != "pulseq/openai-api-key":
            raise Exception(f"unexpected secret: {SecretId}")
        return {"SecretString": secret_value}

    sm = MagicMock()
    sm.get_secret_value.side_effect = _get_secret_value
    return sm


def _make_s3_client():
    return MagicMock()


def _fake_run(base_dir, docs_dir):
    """Simulate writer.run() creating one HTML file."""
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "abc12.html").write_text("<html></html>")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLambdaHandler:
    def setup_method(self):
        # Reset module-level API key cache before each test
        import writer.lambda_handler as lh
        lh._api_key = None

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_happy_path(self, mock_run, mock_boto_client):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["url"].startswith("http://pulseq.s3-website.eu-west-1.amazonaws.com/")
        assert body["url"].endswith(".html")
        s3.upload_file.assert_called_once()
        _, upload_args, upload_kwargs = s3.upload_file.mock_calls[0]
        assert upload_kwargs["ExtraArgs"] == {"ContentType": "text/html"}

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_s3_download_failure(self, mock_run, mock_boto_client):
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
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_api_key_cached_across_calls(self, mock_run, mock_boto_client):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        handler({}, None)
        handler({}, None)

        # Secrets Manager should only be called once despite two handler invocations
        sm.get_secret_value.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=FileNotFoundError("inputs/topic.md not found"))
    def test_writer_run_failure(self, mock_run, mock_boto_client):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "writer.run() failed" in json.loads(result["body"])["error"]

    @patch.dict(os.environ, ENV)
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run", side_effect=_fake_run)
    def test_s3_upload_failure(self, mock_run, mock_boto_client):
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
    @patch("writer.lambda_handler.boto3.client")
    @patch("writer.lambda_handler.run")  # does nothing — produces no HTML
    def test_no_html_produced(self, mock_run, mock_boto_client):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        mock_boto_client.side_effect = lambda svc, **kw: sm if svc == "secretsmanager" else s3

        from writer.lambda_handler import handler
        result = handler({}, None)

        assert result["statusCode"] == 500
        assert "No HTML output produced" in json.loads(result["body"])["error"]
