import os
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    "TOPICS_TABLE": "pulseq-topics",
    "ARTICLES_TABLE": "pulseq-articles",
}

SAMPLE_TOPICS = [
    {"title": "N+1 Queries", "description": "Detection patterns."},
    {"title": "Load Balancers", "description": "Overview."},
]


def _make_topics_table(topics=None):
    table = MagicMock()
    if topics is None:
        table.get_item.return_value = {}
    else:
        table.get_item.return_value = {"Item": {"userId": "user1", "topics": topics}}
    return table


def _make_articles_table(title="Original Article"):
    table = MagicMock()
    table.get_item.return_value = {"Item": {"articleId": "orig-id", "title": title}}
    return table


def _make_ddb_resource(topics_table=None, articles_table=None):
    tt = topics_table or _make_topics_table(SAMPLE_TOPICS)
    at = articles_table or _make_articles_table()

    def table_factory(name):
        if name == "pulseq-topics":
            return tt
        if name == "pulseq-articles":
            return at
        raise ValueError(f"unexpected table: {name}")

    ddb = MagicMock()
    ddb.Table.side_effect = table_factory
    return ddb, tt, at


class TestTopicSelectorHandler:
    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    @patch("writer.topic_selector_handler.generate_short_id", return_value="abc12")
    def test_random_topic_happy_path(self, mock_id, mock_resource):
        ddb, topics_table, _ = _make_ddb_resource()
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        result = handler({"userId": "user1"}, None)

        assert result["userId"] == "user1"
        assert result["articleId"] == "abc12"
        assert "articleTopic" in result
        assert "N+1 Queries" in result["articleTopic"] or "Load Balancers" in result["articleTopic"]
        topics_table.get_item.assert_called_once()
        topics_table.update_item.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    @patch("writer.topic_selector_handler.generate_short_id", return_value="abc12")
    def test_custom_topic_skips_ddb(self, mock_id, mock_resource):
        ddb, topics_table, _ = _make_ddb_resource()
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        result = handler({"userId": "user1", "customTopic": "quantum computing"}, None)

        assert result["articleTopic"] == "quantum computing"
        assert result["articleId"] == "abc12"
        topics_table.get_item.assert_not_called()
        topics_table.update_item.assert_not_called()

    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    @patch("writer.topic_selector_handler.generate_short_id", return_value="abc12")
    def test_follow_up_reads_original_title(self, mock_id, mock_resource):
        ddb, _, articles_table = _make_ddb_resource()
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        result = handler({"userId": "user1", "followUpArticleId": "orig-id"}, None)

        assert result["articleTopic"] == "Original Article"
        assert result["followUpArticleId"] == "orig-id"
        assert "extraContent" not in result
        articles_table.get_item.assert_called_once_with(Key={"articleId": "orig-id"})

    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    @patch("writer.topic_selector_handler.generate_short_id", return_value="abc12")
    def test_follow_up_with_extra_content_concatenates(self, mock_id, mock_resource):
        ddb, _, _ = _make_ddb_resource()
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        result = handler({
            "userId": "user1",
            "followUpArticleId": "orig-id",
            "extraContent": "focus on costs",
        }, None)

        assert result["articleTopic"] == "Original Article — focus on costs"
        assert result["extraContent"] == "focus on costs"

    @patch.dict(os.environ, ENV)
    def test_both_custom_topic_and_follow_up_raises(self):
        from writer.topic_selector_handler import handler
        with patch("writer.topic_selector_handler.logger.error") as error_spy:
            with pytest.raises(ValueError, match="mutually exclusive"):
                handler({
                    "userId": "user1",
                    "customTopic": "quantum",
                    "followUpArticleId": "orig-id",
                }, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    def test_missing_user_id_raises(self):
        from writer.topic_selector_handler import handler
        with patch("writer.topic_selector_handler.logger.error") as error_spy:
            with pytest.raises(ValueError, match="userId"):
                handler({}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    def test_empty_topics_raises(self, mock_resource):
        ddb, _, _ = _make_ddb_resource(topics_table=_make_topics_table([]))
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        with patch("writer.topic_selector_handler.logger.error") as error_spy:
            with pytest.raises(Exception):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    def test_ddb_error_raises(self, mock_resource):
        topics_table = MagicMock()
        topics_table.get_item.side_effect = Exception("DDB error")
        ddb, _, _ = _make_ddb_resource(topics_table=topics_table)
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        with patch("writer.topic_selector_handler.logger.error") as error_spy:
            with pytest.raises(Exception, match="DDB error"):
                handler({"userId": "user1"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    def test_follow_up_article_not_found_raises(self, mock_resource):
        articles_table = MagicMock()
        articles_table.get_item.return_value = {}
        ddb, _, _ = _make_ddb_resource(articles_table=articles_table)
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        with patch("writer.topic_selector_handler.logger.error") as error_spy:
            with pytest.raises(ValueError, match="article not found"):
                handler({"userId": "user1", "followUpArticleId": "missing"}, None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.topic_selector_handler.boto3.resource")
    @patch("writer.topic_selector_handler.generate_short_id", return_value="abc12")
    def test_random_topic_consume_updates_remaining(self, mock_id, mock_resource):
        """Consumed topic is removed; remaining topics are written back."""
        ddb, topics_table, _ = _make_ddb_resource()
        mock_resource.return_value = ddb

        from writer.topic_selector_handler import handler
        result = handler({"userId": "user1"}, None)

        update_call = topics_table.update_item.call_args
        remaining = update_call.kwargs["ExpressionAttributeValues"][":topics"]
        # One topic was consumed, one remains
        assert len(remaining) == 1
