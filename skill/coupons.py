#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""优惠券解析与可用性判断。

`query-my-coupons` 与 `available-coupons` 的返回既不是 JSON 也不是 TOON，
而是**为 Agent 阅读优化的 Markdown 文本** —— 券名、用券价、有效期、适用
渠道都以自然语言写出。本模块把它解析成结构化记录，用于两件事：

    1. 判断某张券此刻是否真的可用（日期范围 / 星期 / 时段三重限制）
    2. 把券关联到具体产品，好让推荐优先考虑「今天正好有券」的那一个

**关于价格**：券面给出的是「用券价格」，但它对应的份数并不总等于 1
（例如「买一送一」是两份）。因此本模块只负责把价格解析出来供展示与排序，
不假定它等于单价，更不会拿它去替代精确的价格核算。

示例文本：

    ## 中薯条买一送一
    - **优惠**: ¥13.5 (用券价格)
    - **有效期**: 2026-10-12 10:30-2026-10-16 23:59 周一、二、三、四、五 10:30-23:59
    - **标签**: 到店专用、外送专用
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Iterable, List, Optional, Sequence, Set

_SECTION = re.compile(r"^##\s+(.+?)\s*$")
_FIELD = re.compile(r"^-\s+\*\*(.+?)\*\*\s*[:：]\s*(.+?)\s*$")
_PRICE = re.compile(r"¥\s*([0-9]+(?:\.[0-9]+)?)")
_DATETIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})")
_WEEKDAY_GROUP = re.compile(r"周([一二三四五六日、，,\s]+)")
_TIME_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})")

_WEEKDAY_INDEX = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}


@dataclass
class Coupon:
    """一张券。"""

    name: str
    price: Optional[float] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    weekdays: Set[int] = field(default_factory=set)
    time_start: Optional[time] = None
    time_end: Optional[time] = None
    tags: List[str] = field(default_factory=list)
    raw: str = ""

    def usable_at(self, moment: datetime) -> bool:
        """这张券在给定时刻是否可用。

        三类限制是「与」的关系：日期范围、星期、时段任意一项不满足即不可用。
        任何一项解析不出来就跳过该项检查 —— 宁可放宽也不误杀，
        因为「有券却没用上」比「多用一张不能用的券」更影响体验。
        """
        if self.start and moment < self.start:
            return False
        if self.end and moment > self.end:
            return False
        if self.weekdays and moment.weekday() not in self.weekdays:
            return False
        if self.time_start and moment.time() < self.time_start:
            return False
        if self.time_end and moment.time() > self.time_end:
            return False
        return True

    def describe(self) -> str:
        price = f"¥{self.price:g}" if self.price is not None else "—"
        return f"{self.name}（用券价 {price}）"


def _parse_time(text: str) -> Optional[time]:
    try:
        hour, minute = text.split(":")
        return time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return None


def _parse_validity(text: str, coupon: Coupon) -> None:
    stamps = [
        datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
        for m in _DATETIME.finditer(text)
    ]
    if stamps:
        coupon.start, coupon.end = stamps[0], stamps[-1]

    group = _WEEKDAY_GROUP.search(text)
    if group:
        coupon.weekdays = {
            _WEEKDAY_INDEX[ch]
            for ch in group.group(1)
            if ch in _WEEKDAY_INDEX
        }

    ranges = _TIME_RANGE.findall(text)
    if ranges:
        coupon.time_start = _parse_time(ranges[-1][0])
        coupon.time_end = _parse_time(ranges[-1][1])


def parse_coupons(text: str) -> List[Coupon]:
    """把券列表文本解析成 Coupon 列表。

    只认 `## 券名` 开头的段落，其余内容（图片、说明文字）一律忽略。
    """
    coupons: List[Coupon] = []
    current: Optional[Coupon] = None
    lines = text.splitlines()

    for line in lines:
        section = _SECTION.match(line)
        if section:
            current = Coupon(name=section.group(1).strip(), raw=line)
            coupons.append(current)
            continue
        if current is None:
            continue
        field_match = _FIELD.match(line)
        if not field_match:
            continue
        key, value = field_match.group(1).strip(), field_match.group(2).strip()
        if "优惠" in key:
            price = _PRICE.search(value)
            if price:
                current.price = float(price.group(1))
        elif "有效期" in key:
            _parse_validity(value, current)
        elif "标签" in key:
            current.tags = [t.strip() for t in re.split(r"[、,，]", value) if t.strip()]
    return coupons


def usable_now(coupons: Sequence[Coupon], moment: Optional[datetime] = None) -> List[Coupon]:
    """筛出此刻可用的券。"""
    moment = moment or datetime.now()
    return [c for c in coupons if c.usable_at(moment)]


def link_to_products(
    coupons: Iterable[Coupon], product_names: Iterable[str]
) -> dict:
    """把券关联到产品名。

    券名通常包含商品名（「中薯条买一送一」→ 中薯条），所以用「产品名是
    券名子串」做关联。返回 {产品名: 券}，同名产品只保留价格最低的那张券。
    """
    mapping: dict = {}
    for product in product_names:
        if len(product) < 2:
            continue
        for coupon in coupons:
            if product not in coupon.name:
                continue
            existing = mapping.get(product)
            if existing is None or (
                coupon.price is not None
                and (existing.price is None or coupon.price < existing.price)
            ):
                mapping[product] = coupon
    return mapping
