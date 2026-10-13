# skill/

项目主体代码目录。

## 当前内容：基础 MCP 客户端

| 文件 | 说明 |
|---|---|
| `mcd_client.py` | 麦当劳 MCP 轻量客户端，仅依赖 Python 标准库 |

`mcd_client.py` 提供任何方向都会用到的基础能力：握手、列出 Tool、调用 Tool。它同时兼容纯 JSON 与 SSE 两种响应体。

### 用法

```bash
export MCD_MCP_TOKEN="<你的 Token>"

# 列出麦当劳 MCP 的全部 Tool
python3 mcd_client.py list

# 调用无参 Tool
python3 mcd_client.py call now-time-info

# 调用带参 Tool
python3 mcd_client.py call query-meals '{"storeId": "12345"}'
```

> **注意**：`create-order`、`cancel-order`、`auto-bind-coupons`、`draw-lottery`、`mall-create-order`、`party-order-create` 为**写操作**，会真实占用账号资源，请勿在未确认的情况下调用。

## 待补充

TODO（定稿前）：本目录将加入项目核心逻辑，具体模块划分随最终选题确定。
