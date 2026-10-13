#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""特制项的营养增减估算。

麦当劳 MCP 会返回一个汉堡有哪些可特制项（去酱、去芝士、去酸黄瓜……），
但 **不返回每一项对应的营养增减量**。也就是说，「去掉芝士能省多少脂肪」
这个数字，接口层面是拿不到的。

本模块用一张自建估算表补上这一环。数值取自常见食材的通用营养参考，
**是估算而非官方数据** —— 所有对外输出都必须带上这个限定，
不能让它看起来像官方数字。

如果将来接口提供了官方数值，只需替换 `MODIFIER_EFFECTS`，
调用方无需改动。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional, Sequence

ESTIMATE_NOTE = "估算值，非官方营养数据"


@dataclass(frozen=True)
class Effect:
    """去掉某一项后，营养的减少量（估算）。"""

    kcal: float = 0.0
    fat: float = 0.0
    protein: float = 0.0
    carb: float = 0.0
    sodium: float = 0.0

    def __add__(self, other: "Effect") -> "Effect":
        return Effect(
            kcal=self.kcal + other.kcal,
            fat=self.fat + other.fat,
            protein=self.protein + other.protein,
            carb=self.carb + other.carb,
            sodium=self.sodium + other.sodium,
        )

    @property
    def empty(self) -> bool:
        return not any((self.kcal, self.fat, self.protein, self.carb, self.sodium))


# 键为匹配关键词：实际名称可能带前后缀，用关键词包含匹配即可覆盖。
# 注意译名不统一：同一类食材在菜单里可能叫「吉士」「芝士」或「干酪片」，
# 三个都要收录，否则会出现「明明点了芝士，却匹配不到」的漏判。
MODIFIER_EFFECTS: Dict[str, Effect] = {
    "吉士": Effect(kcal=50, fat=4.0, protein=3.0, carb=1.0, sodium=150),
    "芝士": Effect(kcal=50, fat=4.0, protein=3.0, carb=1.0, sodium=150),
    "起司": Effect(kcal=50, fat=4.0, protein=3.0, carb=1.0, sodium=150),
    "干酪片": Effect(kcal=50, fat=4.0, protein=3.0, carb=1.0, sodium=150),
    "番茄酱": Effect(kcal=10, fat=0.0, protein=0.0, carb=2.5, sodium=95),
    "芥末酱": Effect(kcal=6, fat=0.3, protein=0.1, carb=1.0, sodium=60),
    "沙拉酱": Effect(kcal=45, fat=4.5, protein=0.1, carb=1.5, sodium=80),
    "酸黄瓜": Effect(kcal=4, fat=0.0, protein=0.0, carb=0.8, sodium=140),
    "洋葱粒": Effect(kcal=3, fat=0.0, protein=0.1, carb=0.7, sodium=1),
    "生菜": Effect(kcal=2, fat=0.0, protein=0.1, carb=0.4, sodium=2),
}


def match_effect(name: str) -> Optional[Effect]:
    """按关键词匹配一项特制（名称可能带后缀，故用包含匹配）。"""
    for key, effect in MODIFIER_EFFECTS.items():
        if key in name:
            return effect
    return None


def estimate_removal(names: Iterable[str]) -> Effect:
    """估算「去掉这些特制项」带来的总营养变化。"""
    total = Effect()
    for name in names:
        effect = match_effect(name)
        if effect:
            total = total + effect
    return total


@dataclass
class Removal:
    """一条去掉建议。"""

    name: str
    effect: Effect
    reason: str

    def describe(self) -> str:
        bits = []
        if self.effect.fat:
            bits.append(f"脂肪 −{self.effect.fat:.0f}g")
        if self.effect.sodium:
            bits.append(f"钠 −{self.effect.sodium:.0f}mg")
        if self.effect.kcal:
            bits.append(f"热量 −{self.effect.kcal:.0f}kcal")
        detail = "、".join(bits) if bits else "影响可忽略"
        return f"{self.name}：{detail}（{self.reason}，{ESTIMATE_NOTE}）"


def available_modifiers(detail: dict) -> List[str]:
    """从 `query-meal-detail` 的返回里取出「可以去掉的特制项」名单。

    只挑当前已选中的（selectedQuantity > 0）—— 已经不加的项无需建议去掉。
    """
    names: List[str] = []
    modification = detail.get("modification") or {}
    for group in modification.get("items", []) or []:
        for value in group.get("values", []) or []:
            name = str(value.get("name", "")).strip()
            if not name:
                continue
            if int(value.get("selectedQuantity", 0) or 0) <= 0:
                continue
            names.append(name)
    return names


def suggest_removals(
    names: Sequence[str],
    *,
    over_fat: float = 0.0,
    over_sodium: float = 0.0,
    max_suggestions: int = 2,
) -> List[Removal]:
    """按超标的维度，建议去掉哪些特制项。

    只做「减法」—— 不新增任何东西。理由是特制项的价值只在减负，
    加料只会让约束更紧，与产品目标相反。
    """
    scored: List[tuple] = []
    for name in names:
        effect = match_effect(name)
        if effect is None or effect.empty:
            continue
        reason_parts = []
        benefit = 0.0
        if over_fat > 0 and effect.fat > 0:
            benefit += effect.fat / max(over_fat, 1.0)
            reason_parts.append("减脂")
        if over_sodium > 0 and effect.sodium > 0:
            benefit += effect.sodium / max(over_sodium, 1.0)
            reason_parts.append("减钠")
        if benefit <= 0:
            continue
        scored.append((benefit, name, effect, "/".join(reason_parts)))

    scored.sort(key=lambda item: -item[0])
    return [
        Removal(name=name, effect=effect, reason=reason)
        for _, name, effect, reason in scored[:max_suggestions]
    ]
