import os
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    "SECRET_NAME": "pulseq/openai-api-key",
    "INPUT_BUCKET": "pulseq-inputs",
    "ARTICLES_TABLE": "pulseq-articles",
    "USER_INBOX_TABLE": "pulseq-user-inbox",
}

SAMPLE_ARTICLE = {
    "id": "abc12",
    "html": "<title>Load Balancers</title><div class=\"header-card\"><h1>Load Balancers</h1></div>",
    "title": "Load Balancers",
    "accent": "#0d9488",
}

ORIGINAL_HTML = "<title>Original Article</title><div class=\"header-card\"><h1>Original Article</h1></div>"

SAMPLE_TAVILY = {
    "results": [
        {"url": "https://example.com/1", "title": "Post 1", "content": "snippet", "score": 0.9},
    ],
    "images": [],
}

BASE_EVENT = {
    "userId": "user1",
    "articleId": "abc12",
    "articleTopic": "Load Balancers — Overview.",
}


def _make_sm_client(api_key="sk-test"):
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": api_key}
    return sm


def _make_s3_client():
    def _get_object(Bucket, Key):
        content = {
            "shared/article_generation_instructions.txt": b"# Article Instructions",
            "shared/follow_up_article_instructions.txt": b"# Follow-up Instructions",
            "user1/user_tastes.md": b"# User Tastes",
        }.get(Key)
        if content is None:
            raise Exception(f"unexpected key: {Key}")
        body = MagicMock()
        body.read.return_value = content
        return {"Body": body}

    s3 = MagicMock()
    s3.get_object.side_effect = _get_object
    return s3


def _make_articles_table():
    return MagicMock()


def _make_inbox_table():
    return MagicMock()


def _make_ddb_resource(articles_table=None, inbox_table=None):
    at = articles_table or _make_articles_table()
    it = inbox_table or _make_inbox_table()

    def table_factory(name):
        if name == "pulseq-articles":
            return at
        if name == "pulseq-user-inbox":
            return it
        raise ValueError(f"unexpected table: {name}")

    ddb = MagicMock()
    ddb.Table.side_effect = table_factory
    return ddb, at, it


def _boto_client_factory(sm=None, s3=None):
    _sm = sm or _make_sm_client()
    _s3 = s3 or _make_s3_client()

    def factory(service, **kwargs):
        if service == "secretsmanager":
            return _sm
        if service == "s3":
            return _s3
        raise ValueError(f"unexpected service: {service}")

    return factory


def _fake_generate_article(article_id, topic, article_instructions, user_tastes, tavily_results=None):
    return {**SAMPLE_ARTICLE, "id": article_id}


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
        ddb, articles_table, inbox_table = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory(sm=sm, s3=s3)
        mock_boto_resource.return_value = ddb

        from writer.article_handler import handler
        result = handler(BASE_EVENT.copy(), None)

        assert result == {"articleId": "abc12", "userId": "user1", "articleTopic": "Load Balancers — Overview.", "articleTitle": "Load Balancers"}

        articles_table.put_item.assert_called_once()
        art_item = articles_table.put_item.call_args.kwargs["Item"]
        assert art_item["articleId"] == "abc12"
        assert art_item["userId"] == "user1"
        assert art_item["title"] == "Load Balancers"
        assert art_item["html"] == SAMPLE_ARTICLE["html"]
        assert "accent" not in art_item
        assert "quiz" not in art_item
        assert isinstance(art_item["creation_timestamp"], str)
        assert art_item["further_reading"] == "[]"

        inbox_table.put_item.assert_called_once()
        inbox_item = inbox_table.put_item.call_args.kwargs["Item"]
        assert inbox_item["userId"] == "user1"
        assert inbox_item["articleId"] == "abc12"
        assert inbox_item["title"] == "Load Balancers"

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_tavily_results_included_in_further_reading(self, mock_gen, mock_boto_client, mock_boto_resource):
        ddb, articles_table, _ = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        event = {**BASE_EVENT, "tavilyResults": SAMPLE_TAVILY}
        from writer.article_handler import handler
        handler(event, None)

        import json
        art_item = articles_table.put_item.call_args.kwargs["Item"]
        further_reading = json.loads(art_item["further_reading"])
        assert further_reading == [{"url": "https://example.com/1", "title": "Post 1"}]

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_malformed_tavily_results_fail_open(self, mock_gen, mock_boto_client, mock_boto_resource):
        ddb, articles_table, _ = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        event = {**BASE_EVENT, "tavilyResults": "not a dict"}
        from writer.article_handler import handler
        with patch("writer.article_handler.logger.warning") as warn_spy:
            result = handler(event, None)

        assert result["articleId"] == "abc12"
        art_item = articles_table.put_item.call_args.kwargs["Item"]
        assert art_item["further_reading"] == "[]"
        warn_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_absent_tavily_results_proceeds_with_empty_further_reading(self, mock_gen, mock_boto_client, mock_boto_resource):
        """When tavilyResults is absent (e.g. Tavily step failed), article generation proceeds and further_reading is []."""
        ddb, articles_table, _ = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        from writer.article_handler import handler
        with patch("writer.article_handler.logger.warning") as warn_spy:
            result = handler(BASE_EVENT.copy(), None)

        assert result["articleId"] == "abc12"
        art_item = articles_table.put_item.call_args.kwargs["Item"]
        assert art_item["further_reading"] == "[]"
        warn_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    def test_missing_user_id_raises(self):
        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(ValueError, match="userId"):
                handler({}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    def test_missing_article_id_raises(self):
        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(ValueError, match="articleId"):
                handler({"userId": "user1", "articleTopic": "topic"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    def test_missing_article_topic_raises(self):
        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(ValueError, match="articleTopic"):
                handler({"userId": "user1", "articleId": "abc12"}, None)
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
                handler(BASE_EVENT.copy(), None)
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
                handler(BASE_EVENT.copy(), None)
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
                handler(BASE_EVENT.copy(), None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_articles_table_save_failure_raises(self, mock_gen, mock_boto_client, mock_boto_resource):
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
                handler(BASE_EVENT.copy(), None)
        error_spy.assert_called_once()

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
        handler(BASE_EVENT.copy(), None)
        handler(BASE_EVENT.copy(), None)

        assert sm.get_secret_value.call_count == 1

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_follow_up_article", return_value={**SAMPLE_ARTICLE})
    def test_follow_up_happy_path(self, mock_follow_up, mock_boto_client, mock_boto_resource):
        """Follow-up path: loads original HTML, saves with sourceArticleId and further_reading."""
        ddb, articles_table, inbox_table = _make_ddb_resource()
        articles_table.get_item.return_value = {"Item": {"articleId": "orig-abc", "html": ORIGINAL_HTML}}
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        from writer.article_handler import handler
        result = handler({
            "userId": "user1",
            "articleId": "abc12",
            "articleTopic": "Original Article — focus on costs",
            "followUpArticleId": "orig-abc",
            "extraContent": "focus on costs",
            "tavilyResults": SAMPLE_TAVILY,
        }, None)

        assert result == {"articleId": "abc12", "userId": "user1", "articleTopic": "Original Article — focus on costs", "articleTitle": "Load Balancers"}
        mock_follow_up.assert_called_once()
        call_kwargs = mock_follow_up.call_args
        assert call_kwargs.args[0] == "abc12"       # article_id
        assert call_kwargs.args[1] == ORIGINAL_HTML  # original_html
        assert call_kwargs.args[2] == "focus on costs"  # extra_content
        assert "# Article Instructions" in call_kwargs.args[4]
        assert "# Follow-up Instructions" in call_kwargs.args[4]

        art_item = articles_table.put_item.call_args.kwargs["Item"]
        assert art_item["sourceArticleId"] == "orig-abc"
        assert art_item["further_reading"] != "[]"

        inbox_item = inbox_table.put_item.call_args.kwargs["Item"]
        assert "sourceArticleId" not in inbox_item

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    def test_follow_up_original_article_not_found_raises(self, mock_boto_client, mock_boto_resource):
        ddb, articles_table, _ = _make_ddb_resource()
        articles_table.get_item.return_value = {}
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        with patch("writer.article_handler.logger.error") as error_spy:
            from writer.article_handler import handler
            with pytest.raises(ValueError, match="article not found"):
                handler({
                    "userId": "user1",
                    "articleId": "abc12",
                    "articleTopic": "topic",
                    "followUpArticleId": "missing-id",
                    "extraContent": "context",
                }, None)
        error_spy.assert_called()

    @patch.dict(os.environ, ENV)
    @patch("writer.article_handler.boto3.resource")
    @patch("writer.article_handler.boto3.client")
    @patch("writer.article_handler.generate_article", side_effect=_fake_generate_article)
    def test_no_topics_table_access(self, mock_gen, mock_boto_client, mock_boto_resource):
        """article_handler no longer accesses TOPICS_TABLE."""
        ddb, _, _ = _make_ddb_resource()
        mock_boto_client.side_effect = _boto_client_factory()
        mock_boto_resource.return_value = ddb

        from writer.article_handler import handler
        handler(BASE_EVENT.copy(), None)

        # Table factory is only called for ARTICLES_TABLE and USER_INBOX_TABLE
        table_names = [call.args[0] for call in ddb.Table.call_args_list]
        assert "pulseq-topics" not in table_names
