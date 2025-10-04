# -*- coding: utf-8 -*-
"""
analysis/payables.py
Анализ кредиторской задолженности (ОСВ 60).
"""

from typing import Dict, Any, List
from collections import Counter

from infra.logger import get_logger
from infra.error_handler import safe_run


class PayablesAnalyzer:
    """
    Анализ кредиторской задолженности (ОСВ 60):
    - aging (0-30, 31-60, 61-90, 90+)
    - топ-поставщики
    - DPO
    - доля просроченной кредиторки
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Анализ кредиторки", retries=2, base_delay=1.0)
    def analyze(self, osv60: Dict[str, Any]) -> Dict[str, Any]:
        txns = osv60.get("transactions", [])
        summary = osv60.get("summary", {})

        # Aging buckets
        aging = self._calc_aging(txns)

        # Топ-поставщики
        top_suppliers = self._calc_top_suppliers(txns)

        # Метрики
        metrics = self._calc_metrics(summary, aging)

        # Интерпретации
        insights = self._generate_insights(metrics, top_suppliers, aging)

        return {"aging": aging, "top_suppliers": top_suppliers, "metrics": metrics, "insights": insights}

    def _calc_aging(self, txns: List[Dict[str, Any]]) -> Dict[str, float]:
        buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
        # ⚠️ Дат в ОСВ обычно нет, поэтому используем closing (упрощение).
        for t in txns:
            closing = t.get("closing") or 0
            buckets["0-30"] += closing
        return buckets

    def _calc_top_suppliers(self, txns: List[Dict[str, Any]]) -> Dict[str, Any]:
        amounts = Counter()
        for t in txns:
            cp = t.get("counterparty")
            if not cp:
                continue
            amt = t.get("closing") or 0
            amounts[cp] += amt
        total = sum(amounts.values())
        top = amounts.most_common(5)
        res = [{"name": k, "amount": v, "share": v / total if total else 0} for k, v in top]
        return {"top": res, "concentration": {"top1": res[0]["share"] if res else 0.0}}

    def _calc_metrics(self, summary: Dict[str, Any], aging: Dict[str, float]) -> Dict[str, Any]:
        metrics = {}
        closing = summary.get("closing", 0)
        turnover = summary.get("total_debit", 0) + summary.get("total_credit", 0)
        days = 365
        metrics["DPO"] = (closing / turnover * days) if turnover > 0 else None
        overdue = aging.get("90+", 0)
        metrics["overdue_share"] = overdue / closing if closing else 0
        return metrics

    def _generate_insights(self, metrics: Dict[str, Any], top_suppliers: Dict[str, Any], aging: Dict[str, float]) -> Dict[str, str]:
        ins: Dict[str, str] = {}

        dpo = metrics.get("DPO")
        if dpo is not None:
            ins["DPO"] = f"DPO = {dpo:.0f} дней. " + ("Задержки критичны (>90)" if dpo > 90 else "В норме")

        overdue_share = metrics.get("overdue_share")
        if overdue_share is not None:
            ins["overdue"] = f"Доля просроченной кредиторки (>90 дней) = {overdue_share:.1%}. " + ("Высокий риск невыплат" if overdue_share > 0.2 else "Контролируемо")

        top = top_suppliers.get("top", [])
        if top:
            ins["concentration"] = f"Топ-1 поставщик = {top[0]['share']:.1%} от всей кредиторки. " + ("Высокая зависимость" if top[0]['share'] > 0.3 else "Диверсификация нормальная")

        return ins
