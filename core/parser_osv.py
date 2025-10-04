# -*- coding: utf-8 -*-
"""
core/parser_osv.py
Парсер оборотно-сальдовых ведомостей (ОСВ) по счетам 60 и 62.
"""

import re
import math
import datetime as dt
from typing import Dict, Any, Union, List, Optional, Tuple
from collections import defaultdict, Counter

import pandas as pd

from infra.logger import get_logger
from infra.error_handler import safe_run

NUM_RE = re.compile(r"-?\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d+)?")
DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")


def _num_to_float(s: Any) -> Optional[float]:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return None
    s = s.replace("\u00A0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


class OSVParser:
    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Парсинг ОСВ", retries=2, base_delay=1.0, backoff=2.0, default={})
    def parse(self, raw_data: Union[pd.DataFrame, str], account_type: str = "62") -> Dict[str, Any]:
        """
        :param raw_data: DataFrame (Excel ОСВ) или текст
        :param account_type: '60' (поставщики) или '62' (покупатели)
        """
        df = self._to_dataframe(raw_data)
        df_norm, colmap = self._normalize_and_map_columns(df)

        txns = self._extract_transactions(df_norm, colmap)

        summary = self._analyze_summary(txns)
        aging = self._aging_analysis(txns)
        concentration = self._concentration_analysis(txns)
        metrics = self._calc_metrics(txns, account_type)

        return {
            "doc_type": f"OSV{account_type}",
            "columns": colmap,
            "transactions": txns,
            "summary": summary,
            "aging": aging,
            "concentration": concentration,
            "metrics": metrics,
        }

    # -------------------------- Подготовка --------------------------

    def _to_dataframe(self, raw: Union[pd.DataFrame, str]) -> pd.DataFrame:
        if isinstance(raw, pd.DataFrame):
            return raw.copy()
        lines = [l.strip() for l in str(raw).splitlines() if l.strip()]
        return pd.DataFrame(lines, columns=["raw"])

    def _normalize_and_map_columns(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
        if df.shape[1] == 1:
            return df.rename(columns={df.columns[0]: "raw"}), {
                "counterparty": "raw", "debit": None, "credit": None, "opening": None, "turnover": None, "closing": None
            }

        headers = df.iloc[0].fillna("").astype(str).str.strip().str.lower().tolist()
        df2 = df.iloc[1:].copy()
        df2.columns = [h or f"col_{i}" for i, h in enumerate(headers)]

        def find(one_of: List[str]) -> Optional[str]:
            for kw in one_of:
                for c in df2.columns:
                    if kw in c.lower():
                        return c
            return None

        colmap = {
            "counterparty": find(["контраг", "постав", "покупат"]),
            "debit": find(["дебет", "дт"]),
            "credit": find(["кредит", "кт"]),
            "opening": find(["начальн", "сальдо"]),
            "turnover": find(["оборот"]),
            "closing": find(["конечн", "сальдо"]),
        }
        return df2.reset_index(drop=True), colmap

    # -------------------------- Извлечение --------------------------

    def _extract_transactions(self, df: pd.DataFrame, colmap: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
        txns: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            cp = str(row[colmap["counterparty"]]) if colmap["counterparty"] else str(row.to_dict())
            debit = _num_to_float(row[colmap["debit"]]) if colmap["debit"] else None
            credit = _num_to_float(row[colmap["credit"]]) if colmap["credit"] else None
            opening = _num_to_float(row[colmap["opening"]]) if colmap["opening"] else None
            turnover = _num_to_float(row[colmap["turnover"]]) if colmap["turnover"] else None
            closing = _num_to_float(row[colmap["closing"]]) if colmap["closing"] else None

            if not any([cp, debit, credit, opening, turnover, closing]):
                continue

            txns.append({
                "counterparty": cp.strip(),
                "debit": debit,
                "credit": credit,
                "opening": opening,
                "turnover": turnover,
                "closing": closing,
            })
        return txns

    # -------------------------- Аналитика --------------------------

    def _analyze_summary(self, txns: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_debit = sum(t["debit"] or 0 for t in txns)
        total_credit = sum(t["credit"] or 0 for t in txns)
        total_open = sum(t["opening"] or 0 for t in txns)
        total_close = sum(t["closing"] or 0 for t in txns)
        return {"total_debit": total_debit, "total_credit": total_credit, "opening": total_open, "closing": total_close}

    def _aging_analysis(self, txns: List[Dict[str, Any]]) -> Dict[str, Any]:
        buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
        today = dt.date.today()
        for t in txns:
            if not t["closing"]:
                continue
            # Эвристика: считаем, что closing ~ дата отчёта; aging делаем по turnover (условно 30 дней)
            # В реальной модели сюда нужно подгружать даты операций.
            age_days = 30  # если нет дат, считаем среднее
            if age_days <= 30:
                buckets["0-30"] += t["closing"]
            elif age_days <= 60:
                buckets["31-60"] += t["closing"]
            elif age_days <= 90:
                buckets["61-90"] += t["closing"]
            else:
                buckets["90+"] += t["closing"]
        return buckets

    def _concentration_analysis(self, txns: List[Dict[str, Any]]) -> Dict[str, Any]:
        amounts = Counter()
        for t in txns:
            amt = (t["closing"] or 0) + (t["turnover"] or 0)
            amounts[t["counterparty"]] += amt
        total = sum(amounts.values())
        top = amounts.most_common(5)
        result = [{"name": k, "amount": v, "share": v / total if total else 0} for k, v in top]
        return {"top": result, "concentration": {"top1": result[0]["share"] if result else 0.0}}

    def _calc_metrics(self, txns: List[Dict[str, Any]], account_type: str) -> Dict[str, Any]:
        summary = self._analyze_summary(txns)
        closing = summary["closing"]
        turnover = summary["total_debit"] + summary["total_credit"]
        days = 365
        if account_type == "62":
            dso = (closing / turnover * days) if turnover > 0 else None
            return {"DSO": dso}
        elif account_type == "60":
            dpo = (closing / turnover * days) if turnover > 0 else None
            return {"DPO": dpo}
        return {}
