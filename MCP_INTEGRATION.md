# MCP 集成说明

本文件说明本项目实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

---

## 1. 接入信息

| 项 | 值 |
|---|---|
| MCP Server | 麦当劳 MCP（`mcd-mcp`） |
| 接口地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（无状态模式） |
| 鉴权方式 | 请求头 `Authorization: Bearer <MCD_MCP_TOKEN>` |
| 协议版本 | `2025-06-18` |
| 速率限制 | 600 次 / 分钟 / Token，超限返回 429 |

配置示例见 [`mcp-config.example.json`](./mcp-config.example.json)，**仓库内不包含任何真实 Token**。

## 2. Tool 总览

麦当劳 MCP 当前对外提供 **35 个 Tool**，按业务域划分为 5 类：

| 业务域 | Tool 数 | Tool 名称 |
|---|---:|---|
| 点餐 / 门店 | 12 | `query-nearby-stores`、`delivery-query-stores`、`delivery-query-addresses`、`delivery-create-address`、`query-meals`、`query-meal-detail`、`query-meal-assistance`、`calculate-price`、`create-order`、`cancel-order`、`query-order`、`order-list` |
| 券 / 活动 | 8 | `available-coupons`、`auto-bind-coupons`、`query-my-coupons`、`query-store-coupons`、`query-survey-coupon`、`query-promotions`、`campaign-calendar`、`now-time-info` |
| 营养 | 1 | `list-nutrition-foods` |
| 积分 / 商城 / 抽奖 | 9 | `query-my-account`、`mall-points-products`、`mall-product-detail`、`mall-create-order`、`mall-order-list`、`mall-order-detail`、`query-lottery-info`、`draw-lottery`、`query-my-prizes` |
| 主题活动 / 派对 | 5 | `query-party-city`、`query-party-store`、`query-party-store-date`、`query-party-store-session`、`party-order-create` |

## 3. 本项目使用的 Tool

TODO（定稿后填写）：只保留本项目真正调用的 Tool，并逐个说明「为什么用、取到了什么、用在产品的哪一步」。

| Tool | 用途 | 产出如何被使用 |
|---|---|---|
| TODO | TODO | TODO |

## 4. 调用流程

TODO（定稿后填写）：用流程图 + 文字说明一次完整调用的编排顺序、并发/串行关系、失败与降级路径。

```
用户输入
   │
   ▼
[ TODO 第一步调用 ]
   │
   ▼
[ TODO 第二步调用 ]
   │
   ▼
产出结果
```

## 5. 业务价值

TODO（定稿后填写）：说明这套 Tool 组合解决了什么真实问题，与「不使用 MCP、纯靠人工或静态数据」相比的增量在哪。

## 6. 工程注意事项

以下为集成过程中确认的事实，供接入方参考：

- **写操作 Tool 需谨慎**：`create-order`、`cancel-order`、`auto-bind-coupons`、`draw-lottery`、`mall-create-order`、`party-order-create` 会真实占用账号资源，接入方应做二次确认，不应在自动化流程中无提示触发。
- **返回格式不统一**：多数 Tool 返回 JSON，但个别 Tool 返回 TOON 格式，直接按 JSON 解析会失败，需先做格式判定。
- **数据完整性**：部分 Tool 返回的字段存在空值或缺省占位，使用前需做校验，不应假定字段必然有值。
- **文档与实现存在差异**：官方文档列出的 Tool 清单与实际接口返回并不完全一致，接入应以 `tools/list` 的实际返回为准。

> 以上仅记录本项目集成时确认的事实与应对方式，不含任何 Token、账号信息或他人数据。
