<p align="center">
  <strong>麦当劳程序员节创意开发大赛 · 参赛作品</strong>
</p>

<h1 align="center">麦当劳 MCP 创意 Skill</h1>

<p align="center"><em>项目名称待定稿 —— 定稿前请替换本行及下方所有 TODO</em></p>

---

## 项目简介

TODO（3–5 句）：谁，在什么场景下，遇到什么问题，这个 Skill 怎么解决。

> 写作要求：不要形容词堆砌，讲清楚「用户不做这件事会损失什么」。

## 为什么值得做

TODO：说明这个痛点真实存在，最好用可验证的数据支撑。

## 功能

| 功能 | 说明 | 状态 |
|---|---|---|
| TODO | TODO | 规划中 |

## 使用的麦当劳 MCP 能力

完整的 Tool 调用清单、调用链路与业务价值说明，见 [MCP_INTEGRATION.md](./MCP_INTEGRATION.md)。

## 快速开始

### 前置条件

| 依赖 | 说明 |
|---|---|
| 麦当劳 MCP Token | 在 <https://open.mcd.cn/mcp> 手机号登录 → 控制台 → 激活后获取 |
| WorkBuddy | 推荐使用，本次活动官方合作伙伴（<https://www.workbuddy.cn/>） |

### 1. 配置麦当劳 MCP

打开 WorkBuddy → 左侧边栏【专家·技能·连接器】→【连接器】页签 → 右上角【自定义连接器】→【配置 MCP】，粘贴以下内容（完整文件见 [`mcp-config.example.json`](./mcp-config.example.json)）：

````json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer ${MCD_MCP_TOKEN}"
      }
    }
  }
}
````

> 把 `${MCD_MCP_TOKEN}` 替换为你的真实 Token 后保存，回到【自定义连接器】将 `mcd-mcp` 启用。

### 2. 使用

TODO：给出 2–3 个真实对话示例（用户说什么 → Skill 做什么 → 产出什么）。

## 目标用户

TODO

## 目录结构

```
.
├── README.md                  # 项目说明（本文件）
├── CONTEST_DECLARATION.md     # 参赛声明（官方原文，不可修改）
├── MCP_INTEGRATION.md         # MCP 集成说明
├── mcp-config.example.json    # 脱敏配置示例
├── workbuddy.md               # WorkBuddy 开发对话记录
└── skill/                     # 项目主体代码
```

## 参赛信息

本仓库为**麦当劳程序员节创意开发大赛**参赛作品。

- 参赛声明：[CONTEST_DECLARATION.md](./CONTEST_DECLARATION.md)
- MCP 集成说明：[MCP_INTEGRATION.md](./MCP_INTEGRATION.md)
- 活动主仓库：[M-China/mcd-developer-innovation-challenge](https://github.com/M-China/mcd-developer-innovation-challenge)

## 声明

本项目为参赛作品，由参赛者独立开发，**非麦当劳官方产品**。项目输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。
