#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦当劳 MCP 轻量客户端（零第三方依赖）。

以 Streamable HTTP 方式连接麦当劳 MCP Server，提供两个基础能力：

    列出全部 Tool      tools/list
    调用指定 Tool      tools/call

环境变量
--------
MCD_MCP_TOKEN   麦当劳 MCP Token（必填）
MCD_MCP_URL     接口地址，默认 https://mcp.mcd.cn

命令行用法
----------
    export MCD_MCP_TOKEN="<你的 Token>"

    # 列出全部 Tool
    python3 mcd_client.py list

    # 调用无参 Tool
    python3 mcd_client.py call now-time-info

    # 调用带参 Tool（参数为 JSON 字符串）
    python3 mcd_client.py call query-meals '{"storeId": "12345"}'
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = 30


def _parse_body(body: str) -> dict:
    """兼容两种响应体：纯 JSON 与 SSE（text/event-stream）。"""
    text = body.strip()
    if not text:
        raise ValueError("响应为空")
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            chunk = line[len("data:"):].strip()
            if chunk and chunk != "[DONE]":
                return json.loads(chunk)
    raise ValueError("无法解析响应：" + text[:200])


class MCDClient:
    """麦当劳 MCP 的极简客户端，仅依赖标准库。"""

    def __init__(self, token: str, url: str = DEFAULT_URL) -> None:
        if not token:
            raise ValueError("缺少 MCD_MCP_TOKEN")
        self.url = url
        self.token = token
        self._seq = 0

    def _next_id(self) -> int:
        self._seq += 1
        return self._seq

    def _request(self, method: str, params: dict | None = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return _parse_body(body)

    def initialize(self) -> dict:
        """握手，返回 serverInfo 等元信息。"""
        return self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcd-skill", "version": "1.0"},
            },
        )

    def list_tools(self) -> list:
        """返回全部可用 Tool 的描述对象列表。"""
        return self._request("tools/list").get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """调用指定 Tool。"""
        return self._request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )


def main(argv: list) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1

    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if not token:
        print("错误：请先设置环境变量 MCD_MCP_TOKEN", file=sys.stderr)
        return 1

    client = MCDClient(token, os.environ.get("MCD_MCP_URL", DEFAULT_URL))
    action = argv[1]

    if action == "list":
        info = client.initialize()
        server = info.get("result", {}).get("serverInfo", {})
        print("Server: " + json.dumps(server, ensure_ascii=False))
        tools = client.list_tools()
        print("共 %d 个 Tool\n" % len(tools))
        for index, tool in enumerate(tools, 1):
            print("%2d. %s" % (index, tool.get("name")))
            desc = (tool.get("description") or "").splitlines()
            if desc and desc[0]:
                print("    " + desc[0][:100])
        return 0

    if action == "call":
        if len(argv) < 3:
            print("用法：mcd_client.py call <tool_name> [json 参数]", file=sys.stderr)
            return 1
        name = argv[2]
        arguments = json.loads(argv[3]) if len(argv) > 3 else {}
        print(json.dumps(client.call_tool(name, arguments), ensure_ascii=False, indent=2))
        return 0

    print("未知命令：" + action, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
