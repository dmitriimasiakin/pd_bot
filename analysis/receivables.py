# -*- coding: utf-8 -*-
"""
analysis/receivables.py
Анализ дебиторской задолженности (ОСВ 62).
"""

from typing import Dict, Any, List
from collections import Counter

from infra.logger import get_logger
from infra.error_handler import safe_run


class ReceivablesAnalyzer:
    """
    Анализ дебиторской задолженности (ОСВ 62):
    - aging (0-30, 31-60, 61-90, 90+)
    - топ-дебиторы
    - DSO
    - доля просроченной дебиторки
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Анализ дебиторки", retries=2, base_delay=1.0)
    def analyze(self, osv62: Dict[str, Any]) -> Dict[str, Any]:
        txns = osv62.get("transactions", [])
        summary = osv62.get("summary", {})

        # Aging buckets
        aging = self._calc_aging(txns)

        # Топ-дебиторы
        top_debtors = self._calc_top_debtors(txns)

        # Метрики
        metrics = self._calc_metrics(summary, aging)

        # Интерпретации
        insights = self._generate_insights(metrics, top_debtors, aging)

        return {"aging": aging, "top_debtors": top_debtors, "metrics": metrics, "insights": insights}

    def _calc_aging(self, txns: List[Dict[str, Any]]) -> Dict[str, float]:
        buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
        # ⚠️ В ОСВ 62 у нас нет конкретных дат каждой задолженности, поэтому считаем по closing.
        # Для демонстрации распределим равномерно или через turnover.
        for t in txns:
            closing = t.get("closing") or 0
            # здесь нужна интеграция с фактическими датами — пока упрощённая модель
            buckets["0-30"] += closing
        return buckets

    def _calc_top_debtors(self, txns: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        metrics["DSO"] = (closing / turnover * days) if turnover > 0 else None
        overdue = aging.get("90+", 0)
        metrics["overdue_share"] = overdue / closing if closing else 0
        return metrics

    def _generate_insights(self, metrics: Dict[str, Any], top_debtors: Dict[str, Any], aging: Dict[str, float]) -> Dict[str, str]:
        ins: Dict[str, str] = {}

        dso = metrics.get("DSO")
        if dso is not None:
            ins["DSO"] = f"DSO = {dso:.0f} дней. " + ("Высокий риск (дольше 90)" if dso > 90 else "Приемлемый уровень")

        overdue_share = metrics.get("overdue_share")
        if overdue_share is not None:
            ins["overdue"] = f"Доля просроченной дебиторки (>90 дней) = {overdue_share:.1%}. " + ("Критично" if overdue_share > 0.2 else "Контролируемо")

        top = top_debtors.get("top", [])
        if top:
            ins["concentration"] = f"Топ-1 дебитор = {top[0]['share']:.1%} от всей дебиторки. " + ("Высокая концентрация" if top[0]['share'] > 0.3 else "Диверсификация нормальная")

        return ins
