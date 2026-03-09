import os
from unittest.mock import patch

import pytest

ENV = {"WRITER_LAMBDA_NAME": "pulseq-writer", "USER_ID": "user1"}


class TestGenerateArticle:
    @patch.dict(os.environ, ENV)
    @patch("mcp_server.server._lambda_client")
    def test_invokes_writer_and_returns_ack(self, mock_client):
        from mcp_server.server import generate_article

        result = generate_article()

        mock_client.invoke.assert_called_once_with(
            FunctionName="pulseq-writer",
            InvocationType="Event",
            Payload=b'{"userId": "user1"}',
        )
        assert "push notification" in result

    @patch.dict(os.environ, ENV)
    @patch("mcp_server.server._lambda_client")
    def test_logs_and_raises_on_invoke_failure(self, mock_client, caplog):
        mock_client.invoke.side_effect = Exception("timeout")

        from mcp_server.server import generate_article

        with pytest.raises(Exception, match="timeout"):
            generate_article()
        assert "failed to invoke writer lambda" in caplog.text

    @patch.dict(os.environ, ENV)
    @patch("mcp_server.server._lambda_client")
    def test_create_app_registers_generate_article_tool(self, mock_client):
        from mcp_server.server import create_app

        mcp = create_app()
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "generate_article" in tool_names
