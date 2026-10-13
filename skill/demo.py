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

from coupons import Coupon, parse_coupons, usable_now  # noqa: E402
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


def build_coupon_map(menu: dict, index: dict, coupons) -> dict:
    """建立「营养名 -> 可用券」的映射。

    做法是**用券名直接匹配营养表** —— 券名本身就带商品名（如「中薯条买一送一」），
    比菜单名更接近营养表的命名方式。再确认该商品确实在售，两者都满足才关联，
    避免推荐出今天根本买不到的券。
    """
    on_sale = set()
    for item in menu.values():
        food = match_food(str(item.get("name", "")), index)
        if food is not None:
            on_sale.add(food.name)

    mapping: dict = {}
    for coupon in coupons:
        food = match_food(coupon.name, index)
        if food is None or food.name not in on_sale:
            continue
        existing = mapping.get(food.name)
        if existing is None or (
            coupon.price is not None
            and (existing.price is None or coupon.price < existing.price)
        ):
            mapping[food.name] = coupon
    return mapping


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

    # 优惠券是加分项：取不到不应阻断主流程，所以整体包在 try 里。
    coupon_map: dict = {}
    try:
        print("→ 读取优惠券 …")
        coupon_text = client.call_tool("query-my-coupons", {"page": "1"})[
            "result"
        ]["content"][0]["text"]
        usable_coupons = usable_now(parse_coupons(coupon_text))
        coupon_map = build_coupon_map(menu, index, usable_coupons)
        print(
            f"  此刻可用 {len(usable_coupons)} 张，"
            f"其中 {len(coupon_map)} 张能对应到在售商品"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  跳过（{type(exc).__name__}）")

    spec = STATES[args.state]
    target = Target(protein=args.protein, kcal=args.kcal, sodium=args.sodium)
    gap = compute_gap(Intake(), target, spec)

    print(f"\n【{spec.label}】{spec.note}")
    print(
        f"缺口：蛋白 {gap.protein:.0f}g ｜ 热量预算 {gap.kcal:.0f}kcal "
        f"｜ 钠预算 {gap.sodium:.0f}mg\n"
    )

    plans = recommend(
        candidates, gap, max_items=2, top_n=args.top, coupon_map=coupon_map
    )
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
