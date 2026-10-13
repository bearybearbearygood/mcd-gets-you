#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""决策层：把「今天的状态」翻译成「这顿该点什么」。

三个概念各管一件事：

    Intake   今天已经吃进去多少（蛋白 / 热量 / 钠 / 脂肪）
    Target   今天的目标是多少
    State    今天是什么状态 —— 它决定「哪些约束可以松、哪些必须守死」

核心思路是「缺口反解」而不是「热量统计」：
不告诉用户今天超了多少，而是算出还缺多少蛋白，再倒推该点哪一样。

State 是这套逻辑的分水岭。同一种营养缺口，在不同状态下答案不同：

    平常日        补蛋白优先，热量与钠都守
    运动 / 重体力  热量预算放宽，钠仍守死
    心情差        允许糖脂超一点，但蛋白不许再缺
    赶时间        快速饱腹，钠仍守死

约束松紧永远只放开一个维度，其余照守 —— 否则个性化就退化成了放任。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations_with_replacement
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from nutrition import Food


@dataclass
class Intake:
    """今日已摄入。"""

    protein: float = 0.0
    kcal: float = 0.0
    fat: float = 0.0
    carb: float = 0.0
    sodium: float = 0.0

    def add(self, food: Food, portions: float = 1.0) -> "Intake":
        return Intake(
            protein=self.protein + food.protein * portions,
            kcal=self.kcal + food.kcal * portions,
            fat=self.fat + food.fat * portions,
            carb=self.carb + food.carb * portions,
            sodium=self.sodium + food.sodium * portions,
        )


@dataclass
class Target:
    """每日目标。

    sodium 是上限而非目标值：它是硬约束，不是要「补足」的量。
    """

    protein: float
    kcal: float
    sodium: float = 2000.0
    fat: Optional[float] = None


@dataclass(frozen=True)
class StateSpec:
    """状态对约束的调整规则。

    kcal_factor / sodium_factor  预算伸缩系数（>1 表示放宽）
    relax                        允许超出的维度，最多一项
    note                         该状态的一句话说明，用于输出给用户
    """

    key: str
    label: str
    note: str
    kcal_factor: float = 1.0
    sodium_factor: float = 1.0
    relax: Tuple[str, ...] = ()


STATES: Dict[str, StateSpec] = {
    "normal": StateSpec(
        key="normal",
        label="平常日",
        note="按标准目标走，蛋白优先，热量与钠都守住。",
    ),
    "workout": StateSpec(
        key="workout",
        label="运动 / 重体力后",
        note="热量预算放宽 20%，优先补回能量与蛋白，钠仍守死。",
        kcal_factor=1.20,
        relax=("kcal",),
    ),
    "mood": StateSpec(
        key="mood",
        label="心情需要照顾",
        note="允许脂肪与碳水适度超出，但蛋白必须补足、钠不放松。",
        kcal_factor=1.10,
        sodium_factor=0.95,
        relax=("fat", "carb"),
    ),
    "rush": StateSpec(
        key="rush",
        label="赶时间 / 加班",
        note="不追求效率最优，选好拿好吃的，钠仍守死。",
    ),
}

DEFAULT_STATE = "normal"


@dataclass
class Gap:
    """缺口：目标减去已摄入。"""

    protein: float
    kcal: float
    sodium: float
    fat: Optional[float]

    @property
    def needs_protein(self) -> bool:
        return self.protein > 0


@dataclass
class PlanItem:
    """方案中的一项。"""

    food: Food
    portions: float = 1.0

    @property
    def protein(self) -> float:
        return self.food.protein * self.portions

    @property
    def kcal(self) -> float:
        return self.food.kcal * self.portions

    @property
    def sodium(self) -> float:
        return self.food.sodium * self.portions


@dataclass
class Plan:
    """一个候选方案，含代价明细。"""

    items: List[PlanItem]
    protein: float = 0.0
    kcal: float = 0.0
    sodium: float = 0.0
    fat: float = 0.0
    carb: float = 0.0
    score: float = 0.0
    cost: Optional[float] = None
    coupons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def protein_per_kcal(self) -> Optional[float]:
        return self.kcal / self.protein if self.protein > 0 else None

    def describe(self) -> str:
        parts = [f"{it.food.name}×{it.portions:g}" for it in self.items]
        text = " + ".join(parts)
        text += f"  →  蛋白 {self.protein:.0f}g / {self.kcal:.0f}kcal"
        text += f" / 钠 {self.sodium:.0f}mg"
        if self.cost is not None:
            text += f" / {self.cost:.1f} 元"
        if self.coupons:
            text += "  【可用券】" + "、".join(self.coupons)
        return text


def compute_gap(intake: Intake, target: Target, spec: StateSpec) -> Gap:
    """按状态调整后的缺口。"""
    kcal_budget = target.kcal * spec.kcal_factor
    sodium_budget = target.sodium * spec.sodium_factor
    fat_budget = target.fat * spec.kcal_factor if target.fat is not None else None
    return Gap(
        protein=max(0.0, target.protein - intake.protein),
        kcal=max(0.0, kcal_budget - intake.kcal),
        sodium=max(0.0, sodium_budget - intake.sodium),
        fat=None if fat_budget is None else max(0.0, fat_budget - intake.fat),
    )


@dataclass
class Weights:
    """评分权重。值越大，该维度越重要。

    默认值体现产品的立场：补足蛋白是第一目标，钠是第二硬约束，
    热量是代价，脂肪是软约束。

    `coupon` 刻意设得比 `protein` 低一个量级：券代表的是「价格」维度，
    它应该只在「营养上打平」时起作用 —— 也就是用户说的
    「双吉也行、麦香鸡也行，但有麦香鸡的券就优先麦香鸡」。
    如果给它太高的权重，有券的低蛋白产品会挤掉营养上更优的方案。
    """

    protein: float = 1.0
    sodium: float = 0.6
    kcal: float = 0.35
    fat: float = 0.25
    cost: float = 0.0
    coupon: float = 0.12


def _sum(items: Sequence[tuple]) -> Plan:
    """把 (食物, 份数) 序列汇总成 Plan。

    同名产品会合并成一项 —— 组合搜索会产生「中薯条×1 + 中薯条×1」这类
    结果，直接展示出来像是点了两样东西，合并成「中薯条×2」才符合直觉。
    """
    merged: Dict[str, PlanItem] = {}
    for food, portions in items:
        if food.name in merged:
            merged[food.name].portions += portions
        else:
            merged[food.name] = PlanItem(food=food, portions=portions)

    plan = Plan(items=list(merged.values()))
    for item in plan.items:
        food, factor = item.food, item.portions
        plan.protein += food.protein * factor
        plan.kcal += food.kcal * factor
        plan.sodium += food.sodium * factor
        plan.fat += food.fat * factor
        plan.carb += food.carb * factor
    return plan


def score_plan(
    plan: Plan,
    gap: Gap,
    weights: Weights,
    coupon_map: Optional[Dict[str, object]] = None,
) -> Tuple[float, List[str]]:
    """给方案打分。分数越高越好；同时返回警告信息。

    评分设计：
        + 补足蛋白缺口（封顶在 1.0，超出的部分不再加分，避免鼓励暴食）
        + 命中可用优惠券（权重远低于蛋白，只在营养打平时起作用）
        - 热量、钠、脂肪超出剩余预算的惩罚
    """
    warnings: List[str] = []
    if gap.protein <= 0:
        return 0.0, warnings

    coverage = min(plan.protein / gap.protein, 1.0)
    value = coverage * weights.protein

    # 优惠券：只记「今天真的可用」的券，命中即加分并记入方案，
    # 供输出层提示用户用哪张券。
    # 券只在「已经补足缺口」的前提下才加分。
    #
    # 用户的原话是「今天点双吉也行、麦香鸡也行，但你正好有麦香鸡的券，
    # 那就推麦香鸡」—— 前提是这两个方案**都能补足**。如果还没补足蛋白
    # 就把券的分加上，会出现「为了用券而牺牲营养」的推荐，本末倒置。
    # 券的记录不受影响，输出层仍然会提示用户这个商品有券可用。
    plan.coupons = []
    if coupon_map:
        for item in plan.items:
            name = item.food.name
            if name in coupon_map and name not in plan.coupons:
                plan.coupons.append(name)
        if plan.coupons and coverage >= 1.0:
            value += weights.coupon * min(len(plan.coupons), 2)

    over_kcal = max(0.0, plan.kcal - gap.kcal)
    over_sodium = max(0.0, plan.sodium - gap.sodium)
    over_fat = max(0.0, plan.fat - gap.fat) if gap.fat is not None else 0.0

    value -= over_kcal / 1000.0 * weights.kcal
    value -= over_sodium / 1000.0 * weights.sodium
    value -= over_fat / 20.0 * weights.fat

    if coverage < 1.0:
        warnings.append(f"蛋白仍缺 {gap.protein - plan.protein:.0f}g")
    if over_sodium > 0:
        warnings.append(f"钠超出 {over_sodium:.0f}mg")
    if over_kcal > 0:
        warnings.append(f"热量超出 {over_kcal:.0f}kcal")
    return value, warnings


def recommend(
    candidates: Iterable[Food],
    gap: Gap,
    *,
    max_items: int = 3,
    max_portions_per_item: int = 2,
    top_n: int = 5,
    weights: Optional[Weights] = None,
    coupon_map: Optional[Dict[str, object]] = None,
) -> List[Plan]:
    """在候选产品中搜索满足缺口的组合。

    candidates 应当是「当前门店在售」且「能匹配到营养数据」的单品集合，
    否则会推荐出用户买不到的东西。

    coupon_map 是「营养名 -> 可用券」的映射，只应传入**此刻真的可用**的券
    （日期、星期、时段三重校验通过）。它只作为次要加分项参与评分。

    搜索空间按组合数增长，所以先用「每克蛋白的热量代价」做一轮筛选，
    把候选压到 min_needed 个以内再枚举。
    """
    weights = weights or Weights()
    if gap.protein <= 0:
        return []

    # 去重：多个菜单项可能映射到同一条营养记录（套餐与单品、别名等），
    # 不去重会在枚举阶段产生完全相同的方案。
    unique: Dict[str, Food] = {}
    for food in candidates:
        unique.setdefault(food.name, food)

    pool = [f for f in unique.values() if f.protein > 0]
    if not pool:
        return []

    pool.sort(key=lambda f: f.kcal_per_protein or 1e9)

    # 剪枝：组合数随候选数增长很快，需要限制规模。
    # 但「今天有可用券」的候选必须**无条件保留** —— 否则会出现
    # 「用户明明有券，推荐里却看不到」，这正是优惠券功能最典型的失效方式。
    favored_names = {f.name for f in pool if coupon_map and f.name in coupon_map}
    favored = [f for f in pool if f.name in favored_names]
    others = [f for f in pool if f.name not in favored_names]

    single_best = pool[0]
    enough = max(1, int(-(-gap.protein // single_best.protein)))  # 向上取整
    limit = max(30, enough * 8)
    pool = favored + others[: max(0, limit - len(favored))]

    best: List[Plan] = []
    for size in range(1, max_items + 1):
        for combo in combinations_with_replacement(pool, size):
            if len({id(f) for f in combo}) > size:
                continue
            portions: List[tuple] = []
            counts: Dict[str, int] = {}
            ok = True
            for food in combo:
                counts[food.name] = counts.get(food.name, 0) + 1
                if counts[food.name] > max_portions_per_item:
                    ok = False
                    break
                portions.append((food, 1))
            if not ok:
                continue

            plan = _sum(portions)
            if plan.kcal > gap.kcal * 1.6:
                continue
            value, warns = score_plan(plan, gap, weights, coupon_map)
            plan.score = value
            plan.warnings = warns
            best.append(plan)

    best.sort(key=lambda p: (-p.score, p.kcal))
    return best[:top_n]


def explain(plan: Plan, gap: Gap, spec: StateSpec) -> str:
    """把方案翻译成人话，含代价明细。"""
    lines = [
        f"【{spec.label}】{spec.note}",
        "",
        f"你今天还缺 {gap.protein:.0f}g 蛋白（剩余热量预算 {gap.kcal:.0f}kcal、"
        f"钠预算 {gap.sodium:.0f}mg）",
        "",
        "推荐：" + plan.describe(),
    ]
    if plan.warnings:
        lines.append("")
        lines.append("代价：" + "；".join(plan.warnings))
    if plan.protein_per_kcal:
        lines.append(f"本次每克蛋白的热量代价：{plan.protein_per_kcal:.1f} kcal/g")
    if plan.coupons:
        lines.append("")
        lines.append(
            "注：标有【可用券】的商品，你名下已有此刻可用的优惠券，下单时记得勾选。"
        )
    return "\n".join(lines)
