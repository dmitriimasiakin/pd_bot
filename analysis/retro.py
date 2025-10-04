# -*- coding: utf-8 -*-
"""
analysis/retro.py
Ретро-симуляция платежей по сделке на истории движения по счёту 51.
"""

from typing import Dict, Any
from infra.logger import get_logger
from infra.error_handler import safe_run


class RetroSimulator:
    """
    Ретро-симуляция:
    - подставляем платежи КП в историю остатков 51
    - считаем shortfall (дефициты)
    - оцениваем вероятность дефолта
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Ретро-симуляция платежей", retries=2, base_delay=1.0)
    def simulate(self, card51: Dict[str, Any], kp: Dict[str, Any]) -> Dict[str, Any]:
        balances = card51.get("balances", {}).get("summary", {}).get("by_month_end", {})
        schedule = kp.get("schedule", {}).get("regular", [])

        # Подготовим платежи по месяцам
        payments_by_month = {}
        for i, p in enumerate(schedule, start=1):
            m = list(balances.keys())[i - 1] if i - 1 < len(balances) else None
            if m:
                payments_by_month[m] = p.get("amount") or 0

        simulation = {}
        total_shortfall = 0
        risky_months = []

        for m, end_balance in balances.items():
            pay = payments_by_month.get(m, 0)
            after = (end_balance or 0) - pay
            default_risk = after < 0
            shortfall = -after if after < 0 else 0
            total_shortfall += shortfall
            if default_risk:
                risky_months.append(m)
            simulation[m] = {
                "end_balance_before": end_balance,
                "payment": pay,
                "end_balance_after": after,
                "default_risk": default_risk,
                "shortfall": shortfall,
            }

        n_total = len(balances)
        n_bad = len(risky_months)
        prob_default = n_bad / n_total if n_total > 0 else None

        metrics = {
            "total_months": n_total,
            "risky_months": risky_months,
            "n_bad": n_bad,
            "prob_default": prob_default,
            "total_shortfall": total_shortfall,
        }

        insights = self._generate_insights(metrics)

        return {"simulation": simulation, "metrics": metrics, "insights": insights}

    def _generate_insights(self, metrics: Dict[str, Any]) -> Dict[str, str]:
        ins: Dict[str, str] = {}

        if metrics.get("prob_default") is not None:
            ins["prob_default"] = f"Вероятность дефолта (ретро-модель) = {metrics['prob_default']:.1%}."

        if metrics.get("n_bad") and metrics["n_bad"] > 0:
            ins["risky_months"] = f"Месяцы с кассовыми разрывами: {', '.join(metrics['risky_months'])}"
            ins["total_shortfall"] = f"Общий shortfall = {metrics['total_shortfall']:,.0f} руб."
        else:
            ins["risky_months"] = "Во всех месяцах хватало средств на платежи."

        return ins
