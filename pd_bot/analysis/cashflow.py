# -*- coding: utf-8 -*-
"""
analysis/cashflow.py
Анализ денежных потоков по карточке счёта 51.
"""

from typing import Dict, Any
from infra.logger import get_logger
from infra.error_handler import safe_run


class CashflowAnalyzer:
    """
    Анализ денежных потоков:
    - динамика cash-in/out
    - DSCR
    - burn-rate
    - выявление кассовых разрывов
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Анализ Cashflow", retries=2, base_delay=1.0)
    def analyze(self, card51: Dict[str, Any], lease_payment: float = 0.0) -> Dict[str, Any]:
        """
        :param card51: результат parser_51
        :param lease_payment: сумма ежемесячного платежа (для DSCR)
        """
        cashflow = card51.get("cashflow", {})
        balances = card51.get("balances", {}).get("summary", {})

        monthly_in = cashflow.get("by_month_in", {})
        monthly_out = cashflow.get("by_month_out", {})

        # Чистый поток по месяцам
        monthly_delta = {m: monthly_in.get(m, 0) - monthly_out.get(m, 0) for m in set(monthly_in) | set(monthly_out)}

        # Метрики
        metrics = {}

        # DSCR = cash-in / lease_payment
        if lease_payment and lease_payment > 0:
            metrics["DSCR_by_month"] = {m: (monthly_in.get(m, 0) / lease_payment) for m in monthly_in}
            metrics["avg_DSCR"] = sum(metrics["DSCR_by_month"].values()) / len(metrics["DSCR_by_month"]) if metrics["DSCR_by_month"] else None
        else:
            metrics["DSCR_by_month"] = {}
            metrics["avg_DSCR"] = None

        # Burn-rate: сколько месяцев компания проживёт при среднем отрицательном потоке
        avg_out = sum(monthly_out.values()) / len(monthly_out) if monthly_out else 0
        if avg_out > 0 and balances.get("daily_avg"):
            metrics["burn_rate_months"] = balances["daily_avg"] / (avg_out / 30)
        else:
            metrics["burn_rate_months"] = None

        # Частота отрицательных остатков
        neg_share = None
        if balances.get("daily_min") is not None and balances.get("daily_min") < 0:
            # считаем, что были отрицательные дни
            neg_share = 1.0
        metrics["negative_balance_share"] = neg_share

        insights = self._generate_insights(metrics, monthly_delta)

        return {
            "monthly": {
                "inflow": monthly_in,
                "outflow": monthly_out,
                "delta": monthly_delta,
            },
            "summary": balances,
            "metrics": metrics,
            "insights": insights,
        }

    def _generate_insights(self, metrics: Dict[str, Any], monthly_delta: Dict[str, float]) -> Dict[str, str]:
        ins: Dict[str, str] = {}

        if metrics.get("avg_DSCR") is not None:
            val = metrics["avg_DSCR"]
            ins["DSCR"] = f"Средний DSCR = {val:.2f}. " + ("Устойчиво" if val >= 1.2 else "Риск дефолта при низком покрытии")

        if metrics.get("burn_rate_months") is not None:
            val = metrics["burn_rate_months"]
            ins["burn_rate"] = f"Burn-rate = {val:.1f} мес. " + ("Запас прочности" if val >= 6 else "Малый запас ликвидности")

        if metrics.get("negative_balance_share") is not None:
            ins["negative_balance"] = "Обнаружены дни с отрицательным остатком → риск кассового разрыва"

        # Проверка по месяцам
        risky_months = [m for m, d in monthly_delta.items() if d < 0]
        if risky_months:
            ins["monthly_risk"] = f"Месяцы с отрицательным потоком: {', '.join(risky_months)}"

        return ins
