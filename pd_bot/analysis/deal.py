# -*- coding: utf-8 -*-
"""
analysis/deal.py
Анализ конкретной сделки на основе КП и финансов клиента.
"""

from typing import Dict, Any, List
from infra.logger import get_logger
from infra.error_handler import safe_run


class DealAnalyzer:
    """
    Анализирует конкретную сделку:
    - нагрузка по платежам из КП
    - сопоставление с денежными потоками (51 счёт)
    - DSCR на уровне сделки
    - выявление рисков кассовых разрывов
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Анализ сделки", retries=2, base_delay=1.0)
    def analyze(self, kp: Dict[str, Any], opu: Dict[str, Any], bal: Dict[str, Any], card51: Dict[str, Any]) -> Dict[str, Any]:
        params = kp.get("params", {})
        schedule = kp.get("schedule", {}).get("regular", [])

        # Данные по компании
        revenue = opu.get("values", {}).get("revenue")
        net_profit = opu.get("values", {}).get("net_profit")
        cashflow = card51.get("cashflow", {})
        monthly_in = cashflow.get("by_month_in", {})

        # Анализ графика платежей
        payments = [p["amount"] for p in schedule if p.get("amount")]
        total_payment = sum(payments) if payments else None
        avg_payment = (total_payment / len(payments)) if payments else None

        payment_analysis = {
            "total_payment": total_payment,
            "avg_payment": avg_payment,
            "num_payments": len(payments),
        }

        # DSCR по сделке = средний inflow / платёж
        risk_analysis = {}
        if avg_payment and monthly_in:
            avg_inflow = sum(monthly_in.values()) / len(monthly_in)
            dscr = avg_inflow / avg_payment if avg_payment > 0 else None
            risk_analysis["deal_DSCR"] = dscr
        else:
            risk_analysis["deal_DSCR"] = None

        # Доля платежа от выручки
        if revenue and avg_payment:
            risk_analysis["payment_vs_revenue"] = avg_payment / revenue
        else:
            risk_analysis["payment_vs_revenue"] = None

        # Доля платежа от среднего inflow
        if avg_payment and monthly_in:
            avg_inflow = sum(monthly_in.values()) / len(monthly_in)
            risk_analysis["payment_vs_inflow"] = avg_payment / avg_inflow if avg_inflow > 0 else None
        else:
            risk_analysis["payment_vs_inflow"] = None

        # Проверка по месяцам (ретро)
        risky_months = []
        if avg_payment and monthly_in:
            for m, inflow in monthly_in.items():
                if inflow < avg_payment:
                    risky_months.append(m)
        risk_analysis["risky_months"] = risky_months

        insights = self._generate_insights(payment_analysis, risk_analysis)

        return {"deal_params": params, "payment_analysis": payment_analysis, "risk_analysis": risk_analysis, "insights": insights}

    def _generate_insights(self, payment_analysis: Dict[str, Any], risk_analysis: Dict[str, Any]) -> Dict[str, str]:
        ins: Dict[str, str] = {}

        if payment_analysis.get("avg_payment"):
            ins["avg_payment"] = f"Средний платёж по КП = {payment_analysis['avg_payment']:,.0f} руб."

        if risk_analysis.get("deal_DSCR") is not None:
            val = risk_analysis["deal_DSCR"]
            ins["deal_DSCR"] = f"DSCR по сделке = {val:.2f}. " + ("Устойчиво" if val >= 1.2 else "Рискованно")

        if risk_analysis.get("payment_vs_revenue") is not None:
            val = risk_analysis["payment_vs_revenue"]
            ins["payment_vs_revenue"] = f"Платёж = {val:.1%} выручки."

        if risk_analysis.get("payment_vs_inflow") is not None:
            val = risk_analysis["payment_vs_inflow"]
            ins["payment_vs_inflow"] = f"Платёж = {val:.1%} среднего inflow по счёту."

        if risk_analysis.get("risky_months"):
            ins["risky_months"] = f"Месяцы с риском кассового разрыва: {', '.join(risk_analysis['risky_months'])}"

        return ins
