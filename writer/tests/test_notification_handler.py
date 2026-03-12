import os
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    "IFTTT_SECRET_NAME": "pulseq/ifttt-key",
    "WEB_BASE_URL": "https://test.example.com",
}

SAMPLE_EVENT = {"articleId": "abc12", "userId": "user1", "articleTitle": "Load Balancers"}


def _make_sm_client():
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": "ifttt-test-key"}
    return sm


class TestNotificationHandler:
    def setup_method(self):
        import writer.notification_handler as nh
        nh._ifttt_key = None

    @patch.dict(os.environ, ENV)
    @patch("writer.notification_handler.urllib.request.urlopen")
    @patch("writer.notification_handler.boto3.client")
    def test_happy_path(self, mock_boto_client, mock_urlopen):
        mock_boto_client.return_value = _make_sm_client()

        from writer.notification_handler import handler
        result = handler(SAMPLE_EVENT, None)

        assert result == {}
        assert mock_urlopen.call_count == 2
        assert mock_urlopen.call_args_list[0].args[0] == "https://test.example.com/api/article/abc12"

    @patch.dict(os.environ, ENV)
    def test_missing_field_raises(self):
        with patch("writer.notification_handler.logger.error") as error_spy:
            from writer.notification_handler import handler
            with pytest.raises(ValueError):
                handler({"userId": "user1", "articleTitle": "X"}, None)
            with pytest.raises(ValueError):
                handler({"articleId": "abc12", "articleTitle": "X"}, None)
            with pytest.raises(ValueError):
                handler({"articleId": "abc12", "userId": "user1"}, None)
        assert error_spy.call_count == 3

    @patch.dict(os.environ, ENV)
    @patch("writer.notification_handler.urllib.request.urlopen")
    @patch("writer.notification_handler.boto3.client")
    def test_warmup_failure_is_nonfatal(self, mock_boto_client, mock_urlopen):
        """Warm-up failure is logged as warning; notification still proceeds."""
        mock_boto_client.return_value = _make_sm_client()
        mock_urlopen.side_effect = [Exception("warm-up timeout"), None]

        with patch("writer.notification_handler.logger.warning") as warn_spy:
            from writer.notification_handler import handler
            result = handler(SAMPLE_EVENT, None)

        assert result == {}
        warn_spy.assert_called_once()
        assert mock_urlopen.call_count == 2

    @patch.dict(os.environ, ENV)
    @patch("writer.notification_handler.urllib.request.urlopen")
    @patch("writer.notification_handler.boto3.client")
    def test_ifttt_failure_raises(self, mock_boto_client, mock_urlopen):
        mock_boto_client.return_value = _make_sm_client()
        mock_urlopen.side_effect = [None, Exception("IFTTT down")]

        with patch("writer.notification_handler.logger.error") as error_spy:
            from writer.notification_handler import handler
            with pytest.raises(Exception, match="IFTTT down"):
                handler(SAMPLE_EVENT, None)
        error_spy.assert_called_once()
