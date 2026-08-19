import time 

from mcp.server import MCPServer

mcp = MCPServer("mock-agent")

@mcp.tool()
def test_tool(mode: str = "success") -> dict:
    if mode == "slow":
        time.sleep(5)
        return {"status": "ok", "value": 42}

    if mode == "error":
        raise RuntimeError("intentional test error (mode=error)")

    if mode == "malformed":
        return {"status": "ok"}

    return {"status": "ok", "value": 42}

if __name__ == "__main__":
    mcp.run(transport="stdio")


