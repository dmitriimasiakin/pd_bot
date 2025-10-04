# -*- coding: utf-8 -*-
"""
core/utils.py
Вспомогательные функции для парсеров и анализа.
"""

import re
import math
import datetime as dt
from typing import List, Any, Optional, Dict
from collections import Counter, defaultdict
import pandas as pd

NUM_RE = re.compile(r"\(?-?\d{1,3}(?:[ \u00A0 ]\d{3})*(?:[.,]\d+)?\)?")
DATE_RE1 = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")
DATE_RE2 = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


# ---------- Числа ----------

def to_float(val: Any) -> Optional[float]:
    """Приведение строки к float: '1 234,56' -> 1234.56 ; '(1 000)' -> -1000.0"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)

    s = str(val).strip()
    if not s:
        return None

    neg = s.startswith("(") and s.endswith(")")
    s = s.replace("(", "").replace(")", "")
    s = s.replace("\u00A0", " ").replace(" ", "").replace(",", ".")
    try:
        x = float(s)
        return -x if neg else x
    except Exception:
        return None


def extract_numbers(text: str) -> List[float]:
    """Извлекает все числа из строки"""
    nums = NUM_RE.findall(text.replace("\u00A0", " "))
    result = []
    for n in nums:
        n = n.replace(" ", "").replace(",", ".").replace("(", "").replace(")", "")
        try:
            result.append(float(n))
        except Exception:
            continue
    return result


def stats(nums: List[float]) -> Dict[str, Optional[float]]:
    """Простейшие статистики"""
    if not nums:
        return {"min": None, "max": None, "avg": None, "sum": 0}
    return {
        "min": min(nums),
        "max": max(nums),
        "avg": sum(nums) / len(nums),
        "sum": sum(nums),
    }


# ---------- Даты ----------

def to_date(val: Any) -> Optional[dt.date]:
    """Парсинг даты из строки"""
    if val is None:
        return None
    if isinstance(val, (dt.date, dt.datetime, pd.Timestamp)):
        return pd.to_datetime(val).date()
    s = str(val)
    m1 = DATE_RE1.search(s)
    if m1:
        return dt.datetime.strptime(m1.group(), "%d.%m.%Y").date()
    m2 = DATE_RE2.search(s)
    if m2:
        return dt.datetime.strptime(m2.group(), "%Y-%m-%d").date()
    return None


def group_by_month(dates: List[dt.date]) -> Dict[str, int]:
    """Группировка дат по месяцам"""
    counter = Counter()
    for d in dates:
        if d:
            counter[d.strftime("%Y-%m")] += 1
    return dict(counter)


def group_by_week(dates: List[dt.date]) -> Dict[str, int]:
    """Группировка дат по неделям"""
    counter = Counter()
    for d in dates:
        if d:
            counter[f"{d.isocalendar()[0]}-W{d.isocalendar()[1]}"] += 1
    return dict(counter)


# ---------- Контрагенты ----------

def extract_inn(text: str) -> List[str]:
    """Извлечение ИНН (10 или 12 цифр)"""
    return re.findall(r"\b\d{10}\b|\b\d{12}\b", text)


def extract_companies(text: str) -> List[str]:
    """Извлечение названий компаний (ООО, ЗАО, АО, ИП)"""
    return re.findall(r"(?:ООО|ЗАО|АО|ИП)\s+[A-Za-zА-Яа-я0-9\"'«»\-\s]{2,}", text, flags=re.IGNORECASE)


def top_counterparties(counterparties: List[str], k: int = 5) -> Dict[str, Any]:
    """ТОП-контрагенты с концентрацией"""
    c = Counter(counterparties)
    top = c.most_common(k)
    total = sum(c.values())
    res = [{"name": name, "count": cnt, "share": cnt / total if total else 0} for name, cnt in top]
    return {
        "top": res,
        "concentration": {
            "top1": res[0]["share"] if res else 0.0,
            "top3": sum(x["share"] for x in res[:3]),
            "top5": sum(x["share"] for x in res[:5]),
        },
    }
