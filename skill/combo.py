#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""套餐拆解与换购优化。

麦当劳的套餐（三件套 / 四件套 / 随心配）在 MCP 里是一组「轮次(course)」，
每轮从若干选项中挑一个。营养表里查不到套餐本身的营养，但子项基本都有，
所以 **套餐的营养必须拆开算，而不是查表**。

拆开之后会多出一个优化维度：**换购本身就有优化空间**。
同一个巨无霸三件套，把可乐换成纯牛奶只加 ¥0.5，蛋白多 7g；
把中薯条换成麦麦脆汁鸡琵琶腿加 ¥3.5，蛋白多 17g。
本模块负责把每一轮的候选枚举出来，按当前缺口挑出最划算的那一种搭配。

价格（含差价）在本模块一并解析并记录，供后续的性价比维度直接使用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import product
from typing import Dict, List, Optional, Sequence

from nutrition import Food, match_food

_DIFF_PRICE = re.compile(r"([+-]?)\s*¥?\s*([0-9]+(?:\.[0-9]+)?)")


def parse_diff_price(text: object) -> float:
    """解析 "+ ¥2.5" / "- ¥0.5" / "+ ¥0" 这类差价文本，单位：元。"""
    if text is None:
        return 0.0
    matched = _DIFF_PRICE.search(str(text))
    if not matched:
        return 0.0
    sign = -1.0 if matched.group(1) == "-" else 1.0
    return sign * float(matched.group(2))


@dataclass
class Option:
    """某一轮里的一个可选项。"""

    code: str
    name: str
    diff_price: float = 0.0
    food: Optional[Food] = None
    is_default: bool = False

    @property
    def usable(self) -> bool:
        """能否参与营养计算（匹配不到营养的子项不参与）。"""
        return self.food is not None


@dataclass
class Course:
    """一个选择轮次。"""

    name: str
    options: List[Option]
    min_qty: int = 1
    max_qty: int = 1

    @property
    def default(self) -> Optional[Option]:
        for option in self.options:
            if option.is_default:
                return option
        return self.options[0] if self.options else None


@dataclass
class Combo:
    """一个套餐。"""

    code: str
    name: str
    price: float
    courses: List[Course] = field(default_factory=list)

    @property
    def enumerable(self) -> bool:
        """当前只支持「每轮恰好选一个」的套餐；更复杂的结构先不做。"""
        return bool(self.courses) and all(
            c.min_qty == 1 and c.max_qty == 1 and c.options for c in self.courses
        )

    @property
    def combination_count(self) -> int:
        total = 1
        for course in self.courses:
            total *= max(1, len(course.options))
        return total


def build_combo(
    detail: dict, index: Dict[str, Food], price: float = 0.0
) -> Combo:
    """把 `query-meal-detail` 返回的 data 转成 Combo。

    index 是营养表的归一化名称索引；匹配不到营养的子项会被保留但标记不可用，
    这样「哪些选项因为缺数据而无法参与计算」是可观测的，而不是悄悄消失。
    """
    courses: List[Course] = []
    for raw_course in detail.get("rounds", []) or []:
        options: List[Option] = []
        for raw in raw_course.get("choices", []) or []:
            name = str(raw.get("name", "")).strip()
            options.append(
                Option(
                    code=str(raw.get("code", "")),
                    name=name,
                    diff_price=parse_diff_price(raw.get("diffPrice")),
                    food=match_food(name, index),
                    is_default=raw.get("isDefault") == 1,
                )
            )
        courses.append(
            Course(
                name=str(raw_course.get("name", "")),
                options=options,
                min_qty=int(raw_course.get("minQuantity", 1) or 1),
                max_qty=int(raw_course.get("maxQuantity", 1) or 1),
            )
        )
    return Combo(
        code=str(detail.get("code", "")),
        name=str(detail.get("name", "")),
        price=price,
        courses=courses,
    )


@dataclass
class Picks:
    """套餐的一种具体搭配。"""

    combo: Combo
    options: List[Option]

    @property
    def price(self) -> float:
        return self.combo.price + sum(o.diff_price for o in self.options)

    @property
    def protein(self) -> float:
        return sum(o.food.protein for o in self.options if o.food)

    @property
    def kcal(self) -> float:
        return sum(o.food.kcal for o in self.options if o.food)

    @property
    def sodium(self) -> float:
        return sum(o.food.sodium for o in self.options if o.food)

    @property
    def fat(self) -> float:
        return sum(o.food.fat for o in self.options if o.food)

    @property
    def missing(self) -> List[str]:
        """因缺少营养数据而无法计入的子项。"""
        return [o.name for o in self.options if not o.food]

    def describe(self) -> str:
        parts = " + ".join(o.name for o in self.options)
        return (
            f"{self.combo.name}（{parts}）  →  "
            f"蛋白 {self.protein:.0f}g / {self.kcal:.0f}kcal / 钠 {self.sodium:.0f}mg"
            f" / {self.price:.1f} 元"
        )


def enumerate_picks(
    combo: Combo, *, skip_unusable: bool = True
) -> List[Picks]:
    """枚举套餐的所有搭配。

    默认跳过含有「营养数据缺失」子项的搭配 —— 少算营养会导致低估代价，
    宁可少给几个候选，也不能给出偏乐观的数字。
    """
    if not combo.enumerable:
        return []
    pools: List[List[Option]] = []
    for course in combo.courses:
        options = [o for o in course.options if (o.usable or not skip_unusable)]
        if not options:
            return []
        pools.append(options)
    return [Picks(combo=combo, options=list(combi)) for combi in product(*pools)]


def _deviation(pick: Picks) -> int:
    """相对默认搭配的偏离度：选了多少个非默认项。"""
    return sum(
        1
        for course, option in zip(pick.combo.courses, pick.options)
        if not option.is_default
    )


def rank_picks(
    picks: Sequence[Picks],
    *,
    protein_gap: float,
    kcal_budget: float,
    sodium_budget: float,
    top_n: int = 5,
) -> List[Picks]:
    """给套餐搭配排序。

    评分遵循一个关键取舍：**热量与钠只在「超出预算」时扣分，低于预算不加分**。
    因为用户要的是「别超」，不是「越低越好」—— 把低热量当成优点，会推出
    「把薯条换成玉米杯」这种用户没要的改动，哪怕蛋白一点没多。

    因此排序主键是「补足蛋白」，次键是「偏离默认搭配的程度」——
    在同样能补足的前提下，改动越少越好。
    """
    scored = []
    for pick in picks:
        if pick.protein <= 0:
            continue
        coverage = min(pick.protein / protein_gap, 1.0) if protein_gap > 0 else 0.0
        value = coverage
        value -= max(0.0, pick.kcal - kcal_budget) / 1000.0 * 0.35
        value -= max(0.0, pick.sodium - sodium_budget) / 1000.0 * 0.35
        scored.append((value, _deviation(pick), pick.kcal, pick))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [item[3] for item in scored[:top_n]]


def swap_advice(default: Optional[Picks], better: Picks) -> List[str]:
    """对比默认搭配与更优搭配，给出「换购建议」文本。

    按**轮次**逐个比对（而不是按选项 code —— 同一轮里换了选项，
    code 本来就不同，用 code 做键永远匹配不上）。
    """
    if default is None or len(default.options) != len(better.options):
        return []
    advice: List[str] = []
    for old, new in zip(default.options, better.options):
        if old.code == new.code:
            continue
        delta = ""
        if old.food and new.food:
            delta = (
                f"（蛋白 {new.food.protein - old.food.protein:+.0f}g、"
                f"钠 {new.food.sodium - old.food.sodium:+.0f}mg、"
                f"差价 {new.diff_price - old.diff_price:+.1f} 元）"
            )
        advice.append(f"{old.name} → {new.name}{delta}")
    return advice
