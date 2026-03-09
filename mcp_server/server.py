import json
import logging
import os

import boto3
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

logger = logging.getLogger(__name__)

# Module-level client — reused across warm invocations
_lambda_client = boto3.client("lambda", region_name="eu-west-1")


def generate_article() -> str:
    """Generate an article from a random topic in the user's PulseQ topic pool."""
    writer_lambda = os.environ["WRITER_LAMBDA_NAME"]
    user_id = os.environ.get("USER_ID", "user1")

    try:
        _lambda_client.invoke(
            FunctionName=writer_lambda,
            InvocationType="Event",
            Payload=json.dumps({"userId": user_id}).encode(),
        )
    except Exception as e:
        logger.error("mcp-server: failed to invoke writer lambda: %s", e)
        raise

    return "Your article is being generated — you'll receive a push notification when it's ready."


def create_app() -> FastMCP:
    """Create a fresh FastMCP instance. Must be called per Lambda invocation
    because StreamableHTTPSessionManager cannot be reused across invocations."""
    mcp = FastMCP(
        "PulseQ",
        stateless_http=True,
        # Disable localhost-only DNS rebinding protection — requests arrive
        # via API Gateway with a public host header.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    mcp.tool()(generate_article)
    return mcp
