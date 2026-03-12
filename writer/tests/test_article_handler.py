import os
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    "SECRET_NAME": "pulseq/openai-api-key",
    "INPUT_BUCKET": "pulseq-inputs",
    "ARTICLES_TABLE": "pulseq-articles",
    "TOPICS_TABLE": "pulseq-topics",
}

SAMPLE_TOPICS = [{"title": "N+1 Queries", "description": "Detection patterns."}]

SAMPLE_ARTICLE = {
    "id": "abc12",
    "html": '<div class="header-card"><h1>Load Balancers</h1></div>',
    "title": "Load Balancers",
    "accent": "#0d9488",
}


def _make_sm_client(api_key="sk-test"):
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": api_key}
    return sm


def _make_s3_client():
    def _get_object(Bucket, Key):
        content = {
            "shared/article_generation_instructions.txt": b"# Article Instructions",
        }.get(Key)
        if content is None:
            raise Exception(f"unexpected key: {Key}")
        body = MagicMock()
        body.read.return_value = content
        return {"Body": body}

    s3 = MagicMock()
    s3.get_object.side_effect = _get_object
    return s3


def _make_topics_table(topics=None):
    table = MagicMock()
    if topics is None:
        table.get_item.return_value = {}
    else:
        table.get_item.return_value = {"Item": {"userId": "user1", "topics": topics}}
    return table


def _make_articles_table():
    return MagicMock()


def _make_ddb_resource(topics_table=None, articles_table=None):
    tt = topics_table or _make_topics_table(SAMPLE_TOPICS)
    at = articles_table or _make_articles_table()
    ddb = MagicMock()
    ddb.Table.side_effect = lambda name: tt if name == "pulseq-topics" else at
    return ddb, tt, at


def _boto_client_factory(sm=None, s3=None):
    """Returns a side_effect for boto3.client that dispatches by service name."""
    _sm = sm or _make_sm_client()
    _s3 = s3 or _make_s3_client()

    def factory(service, **kwargs):
        if service == "secretsmanager":
            return _sm
        if service == "s3":
            return _s3
        raise ValueError(f"unexpected service: {service}")

    return factory


def _fake_generate_article(topic, article_instructions):
    return SAMPLE_ARTICLE.copy()


class TestArticleHandler:
    def setup_method(self):
        import writer.handler_utils as hu
        hu._api_key = None

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_happy_path(self, mock_gen, mock_boto_client, mock_boto_resource):
        sm = _make_sm_client()
        s3 = _make_s3_client()
        ddb, topics_table, articles_table = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory(sm=sm, s3=s3)
        mock_boto_resource.return_value = ddb

        from writer.article_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result == {"articleId": "abc12", "userId": "user1", "articleTitle": "Load Balancers"}
        articles_table.put_item.assert_called_once()
        item = articles_table.put_item.call_args.kwargs["Item"]
        assert item["userid"] == "user1"
        assert item["id"] == "abc12"
        assert item["title"] == "Load Balancers"
        assert "quiz" not in item
        assert isinstance(item["creation_timestamp"], str)
        topics_table.update_item.assert_called_once()

    @patch.dict(os.environ, ENV)
    def test_missing_user_id_raises(self):
        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(ValueError, match="userId"):
                handler({}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.client")
    def test_secret_fetch_failure_raises(self, mock_boto_client):
        sm = MagicMock()
        sm.get_secret_value.side_effect = Exception("AccessDenied")
        mock_boto_client.side_effect = _boto_client_factory(sm=sm)

        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(Exception, match="AccessDenied"):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    def test_s3_failure_raises(self, mock_boto_client, mock_boto_resource):
        s3 = MagicMock()
        s3.get_object.side_effect = Exception("NoSuchKey")
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory(s3=s3)
        mock_boto_resource.return_value = ddb

        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(Exception, match="NoSuchKey"):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    def test_empty_topics_raises(self, mock_boto_client, mock_boto_resource):
        ddb, _, _ = _make_ddb_resource(topics_table=_make_topics_table([]))
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(Exception):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=RuntimeError("gpt down"))
    def test_generate_article_failure_raises(self, mock_gen, mock_boto_client, mock_boto_resource):
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(RuntimeError, match="gpt down"):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_ddb_save_failure_raises(self, mock_gen, mock_boto_client, mock_boto_resource):
        from botocore.exceptions import ClientError
        articles_table = _make_articles_table()
        articles_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "Throttled"}},
            "put_item",
        )
        ddb, _, _ = _make_ddb_resource(articles_table=articles_table)
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(ClientError):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_topic_consume_fail_open(self, mock_gen, mock_boto_client, mock_boto_resource):
        """update_item failure is non-fatal: warning logged, handler still returns result."""
        ddb, topics_table, _ = _make_ddb_resource()
        topics_table.update_item.side_effect = Exception("ConditionalCheckFailed")
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        with patch("writer.article_handler.logger.warning") as warn_spy:
            from writer.article_handler import handler
            result = handler({"userId": "user1"}, None)

        assert result == {"articleId": "abc12", "userId": "user1", "articleTitle": "Load Balancers"}
        warn_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_api_key_cached(self, mock_gen, mock_boto_client, mock_boto_resource):
        sm = _make_sm_client()
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory(sm=sm)
        mock_boto_resource.return_value = ddb

        from writer.article_handler import handler
        handler({"userId": "user1"}, None)
        handler({"userId": "user1"}, None)

        assert sm.get_secret_value.call_count == 1
