"""MCP server for accessing data.gov.hk open data"""

__version__ = "0.3.0a1"
__author__ = "Tony Chan"
__email__ = "chankwongyintony@gmail.com"


def __getattr__(name):
    # Importing an offline/private backend must not construct the public gateway
    # or open its SQLite state. Preserve the legacy explicit `import mcp` API.
    if name == "mcp":
        from .server import mcp

        return mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main():
    from .server import mcp

    mcp.run()
