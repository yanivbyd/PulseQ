import json
import os
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    "SECRET_NAME": "pulseq/openai-api-key",
    "INPUT_BUCKET": "pulseq-inputs",
    "ARTICLES_TABLE": "pulseq-articles",
}

SAMPLE_HTML = '<div class="header-card"><h1>Load Balancers</h1></div>'
SAMPLE_QUIZ = [{"q": "Q?", "options": ["A", "B", "C"], "answer": 0}]

SAMPLE_ARTICLE_ITEM = {
    "id": "abc12",
    "userid": "user1",
    "creation_timestamp": "2026-03-11T08:00:00.000Z",
    "html": SAMPLE_HTML,
    "title": "Load Balancers",
    "accent": "#0d9488",
}


def _make_sm_client():
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": "sk-test"}
    return sm


def _make_s3_client():
    def _get_object(Bucket, Key):
        content = {
            "shared/quiz_generation_instructions.txt": b"# Quiz Instructions",
            "user1/quiz_user_tastes.txt": b"",
        }.get(Key)
        if content is None:
            raise Exception(f"unexpected key: {Key}")
        body = MagicMock()
        body.read.return_value = content
        return {"Body": body}

    s3 = MagicMock()
    s3.get_object.side_effect = _get_object
    return s3


def _make_articles_table(item=SAMPLE_ARTICLE_ITEM):
    table = MagicMock()
    if item is None:
        table.query.return_value = {"Items": []}
    else:
        table.query.return_value = {"Items": [item]}
    return table


def _make_ddb_resource(articles_table=None):
    at = articles_table or _make_articles_table()
    ddb = MagicMock()
    ddb.Table.return_value = at
    return ddb, at


class TestQuizHandler:
    def setup_method(self):
        import writer.handler_utils as hu
        hu._api_key = None

    @patch.dict(os.environ, ENV)
    @patch("writer.quiz_handler.boto3.resource")
    @patch("writer.quiz_handler.boto3.client")
    @patch("writer.handler_utils.boto3.client")
    @patch("writer.quiz_handler.generate_quiz", return_value=SAMPLE_QUIZ)
    @patch("writer.quiz_handler.openai.OpenAI")
    def test_happy_path(self, mock_openai_cls, mock_gen_quiz, mock_utils_client, mock_boto_client, mock_boto_resource):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, articles_table = _make_ddb_resource()
        mock_utils_client.return_value = sm
        mock_boto_client.return_value = s3
        mock_boto_resource.return_value = ddb

        from writer.quiz_handler import handler
        result = handler({"articleId": "abc12", "userId": "user1"}, None)

        assert result == {"articleId": "abc12", "userId": "user1"}
        articles_table.update_item.assert_called_once_with(
            Key={"userid": "user1", "creation_timestamp": SAMPLE_ARTICLE_ITEM["creation_timestamp"]},
            UpdateExpression="SET quiz = :quiz",
            ExpressionAttributeValues={":quiz": json.dumps(SAMPLE_QUIZ)},
        )

    @patch.dict(os.environ, ENV)
    def test_missing_article_id_or_user_id_raises(self):
        with patch("writer.quiz_handler.logger.error") as error_spy:
            from writer.quiz_handler import handler
            with pytest.raises(ValueError):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.handler_utils.boto3.client")
    def test_secret_fetch_failure_raises(self, mock_utils_client):
        sm = MagicMock()
        sm.get_secret_value.side_effect = Exception("Denied")
        mock_utils_client.return_value = sm

        with patch("writer.quiz_handler.logger.error") as error_spy:
            from writer.quiz_handler import handler
            with pytest.raises(Exception, match="Denied"):
                handler({"articleId": "abc12", "userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.quiz_handler.boto3.resource")
    @patch("writer.quiz_handler.boto3.client")
    @patch("writer.handler_utils.boto3.client")
    def test_article_not_found_raises(self, mock_utils_client, mock_boto_client, mock_boto_resource):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, _ = _make_ddb_resource(articles_table=_make_articles_table(item=None))
        mock_utils_client.return_value = sm
        mock_boto_client.return_value = s3
        mock_boto_resource.return_value = ddb

        with patch("writer.quiz_handler.logger.error") as error_spy:
            from writer.quiz_handler import handler
            with pytest.raises(Exception):
                handler({"articleId": "missing", "userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.quiz_handler.boto3.resource")
    @patch("writer.quiz_handler.boto3.client")
    @patch("writer.handler_utils.boto3.client")
    def test_ddb_query_failure_raises(self, mock_utils_client, mock_boto_client, mock_boto_resource):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        at = MagicMock()
        at.query.side_effect = Exception("DDB error")
        ddb, _ = _make_ddb_resource(articles_table=at)
        mock_utils_client.return_value = sm
        mock_boto_client.return_value = s3
        mock_boto_resource.return_value = ddb

        with patch("writer.quiz_handler.logger.error") as error_spy:
            from writer.quiz_handler import handler
            with pytest.raises(Exception, match="DDB error"):
                handler({"articleId": "abc12", "userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.quiz_handler.boto3.resource")
    @patch("writer.quiz_handler.boto3.client")
    @patch("writer.handler_utils.boto3.client")
    def test_s3_failure_raises(self, mock_utils_client, mock_boto_client, mock_boto_resource):
        sm = _make_sm_client()
        s3 = MagicMock()
        s3.get_object.side_effect = Exception("S3 error")
        ddb, _ = _make_ddb_resource()
        mock_utils_client.return_value = sm
        mock_boto_client.return_value = s3
        mock_boto_resource.return_value = ddb

        with patch("writer.quiz_handler.logger.error") as error_spy:
            from writer.quiz_handler import handler
            with pytest.raises(Exception, match="S3 error"):
                handler({"articleId": "abc12", "userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.quiz_handler.boto3.resource")
    @patch("writer.quiz_handler.boto3.client")
    @patch("writer.handler_utils.boto3.client")
    @patch("writer.quiz_handler.generate_quiz", return_value=SAMPLE_QUIZ)
    @patch("writer.quiz_handler.openai.OpenAI")
    def test_ddb_update_failure_raises(self, mock_openai_cls, mock_gen_quiz, mock_utils_client, mock_boto_client, mock_boto_resource):
        from botocore.exceptions import ClientError
        sm = _make_sm_client()
        s3 = _make_s3_client()
        at = _make_articles_table()
        at.update_item.side_effect = ClientError(
            {"Error": {"Code": "Throttled", "Message": "Throttled"}}, "update_item"
        )
        ddb, _ = _make_ddb_resource(articles_table=at)
        mock_utils_client.return_value = sm
        mock_boto_client.return_value = s3
        mock_boto_resource.return_value = ddb

        with patch("writer.quiz_handler.logger.error") as error_spy:
            from writer.quiz_handler import handler
            with pytest.raises(ClientError):
                handler({"articleId": "abc12", "userId": "user1"}, None)
        error_spy.assert_called_once()
