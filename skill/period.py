#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时段感知：把「现在几点」翻译成「这顿饭该怎么吃」。

麦当劳的菜单本身是分时段的（早餐、正餐、下午茶、夜宵的菜品不同），
`query-meals` 会按服务端当前时间返回对应时段能点到的菜品 —— 这一层接口
已经帮我们做掉了。

但「时段」还影响另一件更根本的事：**这顿饭在一天里的位置不同，目标就该不同**。

    早餐   = 一天的第一顿：启动代谢，蛋白要够，碳水可以放宽一点
    午餐   = 承上启下：按标准目标走
    下午茶 = 小补一口：别影响晚餐
    晚餐   = 今天最后一顿：总量收着点，但蛋白别缺（睡前蛋白合成用得上）
    夜宵   = 尽量轻：避免高脂高碳水影响睡眠

于是「早上 8 点问吃什么」和「晚上 8 点问吃什么」，即使缺口一样，
答案也不一样 —— 前者可能推荐带碳水的启动型组合，后者更偏向控制总量。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as _time
from typing import Optional


@dataclass(frozen=True)
class Period:
    """一个时段及其对营养目标的影响。"""

    key: str
    label: str
    note: str
    kcal_factor: float = 1.0
    protein_factor: float = 1.0
    carb_soften: bool = False
    fat_soften: bool = False

    def describe(self) -> str:
        return f"{self.label} · {self.note}"


_PERIODS = {
    "breakfast": Period(
        key="breakfast",
        label="早餐",
        note="一天的开始，启动代谢：蛋白要够，碳水可以放宽一点。",
        kcal_factor=1.0,
        protein_factor=1.0,
        carb_soften=True,
    ),
    "lunch": Period(
        key="lunch",
        label="午餐",
        note="承上启下的主力一顿，按标准目标走。",
    ),
    "afternoon": Period(
        key="afternoon",
        label="下午茶",
        note="小补一口，别影响晚餐。",
        kcal_factor=0.4,
        protein_factor=0.4,
    ),
    "dinner": Period(
        key="dinner",
        label="晚餐",
        note="今天最后一顿，总量收着点，但蛋白别缺。",
        kcal_factor=0.85,
        protein_factor=1.0,
    ),
    "late_night": Period(
        key="late_night",
        label="夜宵",
        note="尽量轻，避免高脂高碳水影响睡眠。",
        kcal_factor=0.5,
        protein_factor=0.5,
    ),
}

# 时段边界（小时:分钟）。麦当劳的预约时段本身有 14 分钟的固定偏移，
# 这里用整洁的整点/半点做边界，不影响判断结果。
_BOUNDS = [
    ("late_night", _time(0, 0)),
    ("breakfast", _time(5, 0)),
    ("lunch", _time(10, 30)),
    ("afternoon", _time(14, 30)),
    ("dinner", _time(17, 0)),
    ("late_night", _time(21, 30)),
]


def classify_period(moment: Optional[datetime] = None) -> Period:
    """判断某个时刻属于哪个时段。默认取当前时刻。

    用「小于下一个边界」来归位：先按边界排序，落在最后一段的归夜宵。
    """
    moment = moment or datetime.now()
    t = moment.time()
    current = "late_night"
    for key, start in sorted(_BOUNDS, key=lambda pair: pair[1]):
        if t >= start:
            current = key
    return _PERIODS[current]


def list_periods() -> list:
    """按一天顺序返回所有时段（供文档或展示用）。"""
    order = ["breakfast", "lunch", "afternoon", "dinner", "late_night"]
    return [_PERIODS[k] for k in order]
