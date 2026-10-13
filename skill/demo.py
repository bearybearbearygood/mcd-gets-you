#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端演示：从「今天缺什么」到「这顿点什么」。

用法：

    export MCD_MCP_TOKEN="你的 Token"
    python3 skill/demo.py --protein 40 --kcal 1200 --sodium 1400

    # 换一种状态：运动后 / 心情需要照顾 / 赶时间
    python3 skill/demo.py --state workout --protein 45
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcd_client import DEFAULT_URL, MCDClient  # noqa: E402
from nutrition import (  # noqa: E402
    build_index,
    extract_payload,
    load_from_tool_text,
    match_food,
)
from planner import (  # noqa: E402
    STATES,
    Intake,
    Target,
    compute_gap,
    recommend,
)


def fetch(client: MCDClient, tool: str, args: dict) -> dict:
    text = client.call_tool(tool, args)["result"]["content"][0]["text"]
    return extract_payload(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="麦麦懂你 · 端到端演示")
    parser.add_argument("--city", default="北京市", help="城市名")
    parser.add_argument("--keyword", default="国贸", help="位置关键词")
    parser.add_argument("--state", default="normal", choices=sorted(STATES), help="今日状态")
    parser.add_argument("--protein", type=float, default=40.0, help="今天还缺多少蛋白（g）")
    parser.add_argument("--kcal", type=float, default=1200.0, help="剩余热量预算（kcal）")
    parser.add_argument("--sodium", type=float, default=1400.0, help="剩余钠预算（mg）")
    parser.add_argument("--top", type=int, default=3, help="展示几个方案")
    args = parser.parse_args()

    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if not token:
        print("请先设置环境变量 MCD_MCP_TOKEN", file=sys.stderr)
        return 1
    client = MCDClient(token, os.environ.get("MCD_MCP_URL", DEFAULT_URL))

    print("→ 拉取营养表 …")
    table = client.call_tool("list-nutrition-foods")["result"]["content"][0]["text"]
    foods = load_from_tool_text(table)
    print(f"  {len(foods)} 条")

    print(f"→ 检索门店（{args.city} / {args.keyword}）…")
    stores = fetch(
        client,
        "query-nearby-stores",
        {"beType": 1, "city": args.city, "keyword": args.keyword, "searchType": 2},
    ).get("data") or []
    if not stores:
        print("  未找到门店，换个关键词试试", file=sys.stderr)
        return 1
    store = stores[0]
    print(f"  {store.get('storeName')}（{store.get('storeCode')}）")

    print("→ 拉取在售菜单 …")
    menu = fetch(
        client,
        "query-meals",
        {"storeCode": store["storeCode"], "orderType": 1, "beType": 1},
    )["data"]["meals"]
    index = build_index(foods)
    candidates = [
        food
        for food in (match_food(item.get("name", ""), index) for item in menu.values())
        if food
    ]
    usable = len({food.name for food in candidates})
    print(f"  {len(menu)} 项在售，其中 {usable} 项能匹配到营养数据")

    spec = STATES[args.state]
    target = Target(protein=args.protein, kcal=args.kcal, sodium=args.sodium)
    gap = compute_gap(Intake(), target, spec)

    print(f"\n【{spec.label}】{spec.note}")
    print(
        f"缺口：蛋白 {gap.protein:.0f}g ｜ 热量预算 {gap.kcal:.0f}kcal "
        f"｜ 钠预算 {gap.sodium:.0f}mg\n"
    )

    plans = recommend(candidates, gap, max_items=2, top_n=args.top)
    if not plans:
        print("没有找到合适方案。")
        return 0
    for i, plan in enumerate(plans, 1):
        print(f"{i}. {plan.describe()}")
        if plan.warnings:
            print("   代价：" + "；".join(plan.warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
