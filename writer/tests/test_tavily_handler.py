import json
import os
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    "TAVILY_SECRET_NAME": "pulseq/tavily-api-key",
}

SAMPLE_TAVILY_RESPONSE = {
    "results": [
        {"url": "https://example.com/post1", "title": "Post 1", "content": "snippet 1", "score": 0.9},
        {"url": "https://example.com/post2", "title": "Post 2", "content": "snippet 2", "score": 0.8},
    ],
    "images": [{"url": "https://example.com/img1.png", "description": "Image 1"}],
    "query": "Blog posts related to Load Balancers",
    "response_time": 1.23,
}

BASE_EVENT = {
    "userId": "user1",
    "articleId": "abc12",
    "articleTopic": "Load Balancers",
}


def _make_sm_client(api_key="tvly-test"):
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": api_key}
    return sm


class TestTavilyHandler:
    @patch.dict(os.environ, ENV)
    @patch("writer.tavily_handler.boto3.client")
    @patch("writer.tavily_handler.call_tavily")
    def test_happy_path_passes_through_event_and_adds_results(self, mock_call, mock_boto):
        mock_boto.return_value = _make_sm_client()
        mock_call.return_value = SAMPLE_TAVILY_RESPONSE

        from writer.tavily_handler import handler
        result = handler(BASE_EVENT.copy(), None)

        assert result["userId"] == "user1"
        assert result["articleId"] == "abc12"
        assert result["articleTopic"] == "Load Balancers"
        assert result["tavilyResults"] == SAMPLE_TAVILY_RESPONSE
        mock_call.assert_called_once_with("tvly-test", "Load Balancers")

    @patch.dict(os.environ, ENV)
    @patch("writer.tavily_handler.boto3.client")
    @patch("writer.tavily_handler.call_tavily")
    def test_logs_payload_size(self, mock_call, mock_boto):
        mock_boto.return_value = _make_sm_client()
        mock_call.return_value = SAMPLE_TAVILY_RESPONSE

        from writer.tavily_handler import handler
        with patch("writer.tavily_handler.logger.info") as info_spy:
            handler(BASE_EVENT.copy(), None)

        logged_messages = [str(c) for c in info_spy.call_args_list]
        assert any("payload size" in m for m in logged_messages)

    @patch.dict(os.environ, ENV)
    @patch("writer.tavily_handler.boto3.client")
    @patch("writer.tavily_handler.call_tavily")
    def test_warns_when_payload_exceeds_200kb(self, mock_call, mock_boto):
        mock_boto.return_value = _make_sm_client()
        large_response = {"results": [{"url": "x", "title": "t", "content": "x" * 50000}] * 5, "images": []}
        mock_call.return_value = large_response

        from writer.tavily_handler import handler
        with patch("writer.tavily_handler.logger.warning") as warn_spy:
            handler(BASE_EVENT.copy(), None)

        warn_spy.assert_called_once()
        assert "200 KB" in str(warn_spy.call_args) or "200" in str(warn_spy.call_args)

    @patch.dict(os.environ, ENV)
    @patch("writer.tavily_handler.boto3.client")
    @patch("writer.tavily_handler.call_tavily")
    def test_tavily_error_raises_and_logs(self, mock_call, mock_boto):
        mock_boto.return_value = _make_sm_client()
        mock_call.side_effect = Exception("Tavily timeout")

        from writer.tavily_handler import handler
        with patch("writer.tavily_handler.logger.error") as error_spy:
            with pytest.raises(Exception, match="Tavily timeout"):
                handler(BASE_EVENT.copy(), None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    @patch("writer.tavily_handler.boto3.client")
    def test_secrets_manager_error_raises_and_logs(self, mock_boto):
        sm = MagicMock()
        sm.get_secret_value.side_effect = Exception("AccessDenied")
        mock_boto.return_value = sm

        from writer.tavily_handler import handler
        with patch("writer.tavily_handler.logger.error") as error_spy:
            with pytest.raises(Exception, match="AccessDenied"):
                handler(BASE_EVENT.copy(), None)
        error_spy.assert_called_once()

    @patch.dict(os.environ, ENV)
    def test_missing_article_topic_raises_and_logs(self):
        from writer.tavily_handler import handler
        with patch("writer.tavily_handler.logger.error") as error_spy:
            with pytest.raises(ValueError, match="articleTopic"):
                handler({"userId": "user1", "articleId": "abc12"}, None)
        error_spy.assert_called_once()
