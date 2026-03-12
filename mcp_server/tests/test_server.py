import os
from unittest.mock import patch

import pytest

ENV = {
    "WRITER_STATE_MACHINE_ARN": "arn:aws:states:eu-west-1:123456789012:stateMachine:WriterSM",
    "USER_ID": "user1",
}


class TestGenerateArticle:
    @patch.dict(os.environ, ENV)
    @patch("mcp_server.server._sfn_client")
    def test_starts_execution_and_returns_ack(self, mock_client):
        from mcp_server.server import generate_article

        result = generate_article()

        mock_client.start_execution.assert_called_once_with(
            stateMachineArn=ENV["WRITER_STATE_MACHINE_ARN"],
            input='{"userId": "user1"}',
        )
        assert "push notification" in result

    @patch.dict(os.environ, ENV)
    @patch("mcp_server.server._sfn_client")
    def test_logs_and_raises_on_failure(self, mock_client, caplog):
        mock_client.start_execution.side_effect = Exception("timeout")

        from mcp_server.server import generate_article

        with pytest.raises(Exception, match="timeout"):
            generate_article()
        assert "failed to start state machine execution" in caplog.text

    @patch.dict(os.environ, ENV)
    @patch("mcp_server.server._sfn_client")
    def test_create_app_registers_generate_article_tool(self, mock_client):
        from mcp_server.server import create_app

        mcp = create_app()
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "generate_article" in tool_names
