from mangum import Mangum

try:
    from server import create_app  # Lambda: server.py at bundle root
except ImportError:
    from mcp_server.server import create_app  # type: ignore[no-redef]  # Tests: package import


def handler(event, context):
    # Fresh FastMCP instance per invocation — StreamableHTTPSessionManager
    # cannot be reused across Lambda warm invocations (run() can only be called once).
    app = create_app().streamable_http_app()
    return Mangum(app, lifespan="on")(event, context)
