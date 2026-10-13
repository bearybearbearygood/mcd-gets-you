#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据层：营养表的解析、指标计算与名称映射。

麦当劳 MCP 的 `list-nutrition-foods` 返回的是一段 TOON 格式字符串，
形如：

    [160]{productName,nutritionDescription,energyKcal,protein,fat,...}:
      巨无霸,null,513,27,26,42,961,171
      板烧鸡腿堡,null,391,23,17,35,1041,93

本模块负责三件事：
    1. 解析 TOON（以及从工具返回的说明文本中提取原始 JSON）
    2. 计算选品用的派生指标（每克蛋白的热量/钠/脂肪代价）
    3. 在「菜单名称」与「营养表名称」之间做映射

第 3 点是最脏的一块：菜单与营养表是两套独立的产品命名，
实测 117 个在售产品中只有约 19 个能精确匹配。这里的策略是
「精确匹配 → 归一化匹配 → 关键词包含」，并把无法匹配的记录
显式暴露出来，而不是静默丢弃。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

_TOON_HEADER = re.compile(r"^\[(\d+)\]\{([^}]+)\}:\s*$")
_ORIGINAL_MARK = "## Original Response"
_STRIP_CHARS = re.compile(r"[\s（）()【】\[\]·・\-—－_"r"'\"“”‘’]+")


@dataclass
class Food:
    """一条营养记录。"""

    name: str
    kcal: float = 0.0
    protein: float = 0.0
    fat: float = 0.0
    carb: float = 0.0
    sodium: float = 0.0
    calcium: float = 0.0
    raw: Dict[str, str] = field(default_factory=dict)

    @property
    def kcal_per_protein(self) -> Optional[float]:
        """每克蛋白要付出的热量代价（越低越划算）。"""
        return self.kcal / self.protein if self.protein > 0 else None

    @property
    def sodium_per_protein(self) -> Optional[float]:
        """每克蛋白附带的钠负担，单位 mg（越低越好）。"""
        return self.sodium / self.protein if self.protein > 0 else None

    @property
    def fat_per_protein(self) -> Optional[float]:
        """每克蛋白附带的脂肪，单位 g。"""
        return self.fat / self.protein if self.protein > 0 else None

    @property
    def fat_energy_ratio(self) -> Optional[float]:
        """脂肪供能占比，单位 %。"""
        return self.fat * 9 / self.kcal * 100 if self.kcal > 0 else None

    def scaled(self, factor: float) -> "Food":
        """按份数缩放，用于「补足 N 克蛋白需要吃几份」这类计算。"""
        return Food(
            name=self.name,
            kcal=self.kcal * factor,
            protein=self.protein * factor,
            fat=self.fat * factor,
            carb=self.carb * factor,
            sodium=self.sodium * factor,
            calcium=self.calcium * factor,
        )


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def extract_payload(text: str) -> dict:
    """从工具返回的文本中提取原始 JSON 对象。

    各工具的响应格式并不统一：部分工具用 "## Original Response" 作为分隔，
    部分工具直接把 JSON 接在说明文字之后；且 JSON 之后常带尾随文本。

    因此这里不假设固定分隔符，而是扫描文本中第一个可成功解析的 `{`，
    并用 raw_decode 只消费一个完整的 JSON 对象。
    """
    body = text.split(_ORIGINAL_MARK, 1)[-1] if _ORIGINAL_MARK in text else text
    decoder = json.JSONDecoder()
    for i, ch in enumerate(body):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(body[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("未能从工具响应中提取 JSON：" + text[:120])


def parse_toon(text: str) -> List[Food]:
    """把 TOON 文本解析成 Food 列表。

    列名以首行的 `{...}` 为准，不做位置假设；行内字段数与表头不一致的
    记录会被跳过（静默损坏的数据比缺数据更危险）。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    matched = _TOON_HEADER.match(lines[0].strip())
    if not matched:
        raise ValueError("不是合法的 TOON 表头: " + lines[0][:80])

    fields = [f.strip() for f in matched.group(2).split(",")]
    index = {name: i for i, name in enumerate(fields)}
    out: List[Food] = []

    for line in lines[1:]:
        cells = line.strip().split(",")
        if len(cells) != len(fields):
            continue
        raw = {name: cells[i] for name, i in index.items()}
        name = (raw.get("productName") or "").strip()
        if not name:
            continue
        out.append(
            Food(
                name=name,
                kcal=_num(raw.get("energyKcal")),
                protein=_num(raw.get("protein")),
                fat=_num(raw.get("fat")),
                carb=_num(raw.get("carbohydrate")),
                sodium=_num(raw.get("sodium")),
                calcium=_num(raw.get("calcium")),
                raw=raw,
            )
        )
    return out


def dedupe(foods: Iterable[Food]) -> List[Food]:
    """去掉完全重复的记录（实测数据源中存在同名同值的重复行）。"""
    seen = set()
    out = []
    for food in foods:
        key = (
            food.name,
            food.kcal,
            food.protein,
            food.fat,
            food.carb,
            food.sodium,
            food.calcium,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(food)
    return out


def load_from_tool_text(text: str) -> List[Food]:
    """便捷入口：直接从 MCP 工具返回的文本得到去重后的 Food 列表。"""
    payload = extract_payload(text)
    toon = payload.get("data")
    if not isinstance(toon, str):
        return []
    return dedupe(parse_toon(toon))


def normalize_name(name: str) -> str:
    """归一化产品名，用于跨数据源匹配。

    只剔除排版性差异（括号、连接符、空白、引号），不改变语义词序。
    """
    return _STRIP_CHARS.sub("", name)


def build_index(foods: Iterable[Food]) -> Dict[str, Food]:
    """构建归一化名称 -> Food 的索引。重名时保留第一条。"""
    index: Dict[str, Food] = {}
    for food in foods:
        index.setdefault(normalize_name(food.name), food)
    return index


_MIN_PREFIX = 4
_PREFIX_RATIO = 0.6

# 套餐类关键词。菜单里「X 三件套」与营养表里「X」是两个不同的东西
# （套餐含薯条与饮料，蛋白与钠都显著更高），模糊匹配时必须区分，
# 否则会把套餐的营养当成单品来算。
_COMBO_MARKERS = (
    "套餐",
    "三件套",
    "四件套",
    "两件套",
    "随心配",
    "分享餐",
    "组合",
)


def _is_combo(name: str) -> bool:
    return any(mark in name for mark in _COMBO_MARKERS)


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def match_food(menu_name: str, index: Dict[str, Food]) -> Optional[Food]:
    """把菜单产品名映射到营养记录。

    三级策略，从严格到宽松：
        1. 归一化后完全相同
        2. 归一化后一方包含另一方（且套餐结构一致）
        3. 共同前缀足够长（先去口味修饰，再比主干，同样要求结构一致）

    匹配错了比匹配不上更危险：前者会给出错误的营养数据，后者只是少一个
    候选。因此模糊匹配既设长度门槛，也比对「是否为套餐」。
    """
    key = normalize_name(menu_name)
    if not key:
        return None
    if key in index:
        return index[key]

    menu_is_combo = _is_combo(menu_name)

    for candidate_key, food in index.items():
        if len(candidate_key) < _MIN_PREFIX:
            continue
        if candidate_key in key or key in candidate_key:
            if menu_is_combo == _is_combo(food.name):
                return food

    core = _core_name(key)
    best: Optional[Food] = None
    best_len = 0
    for other_key, food in index.items():
        if menu_is_combo != _is_combo(food.name):
            continue
        other_core = _core_name(other_key) if core != key else other_key
        if not other_core:
            continue
        if core and other_core == core:
            return food
        n = _common_prefix_len(core, other_core)
        if n >= _MIN_PREFIX and n >= min(len(core), len(other_core)) * _PREFIX_RATIO:
            if n > best_len:
                best, best_len = food, n
    return best


_FLAVOR_PREFIX = re.compile(
    r"^(?:[^a-zA-Z]*?(?:风味|口味))|^(?:蒜了吧|蜜汁BBQ|柠萌|原味|香辣|麻辣|黑椒)"
)


def _core_name(key: str) -> str:
    """去掉口味修饰，保留产品主干，用于宽松匹配。"""
    prev = None
    out = key
    while prev != out:
        prev = out
        out = _FLAVOR_PREFIX.sub("", out)
    return out


def coverage(menu_names: Iterable[str], foods: Iterable[Food]) -> Dict[str, object]:
    """统计菜单与营养表的匹配覆盖率，用于开发期体检。"""
    index = build_index(foods)
    hit, miss = [], []
    for name in menu_names:
        (hit if match_food(name, index) else miss).append(name)
    return {"total": len(hit) + len(miss), "matched": len(hit), "missed": miss}
