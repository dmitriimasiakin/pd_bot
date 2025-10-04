# -*- coding: utf-8 -*-
"""
analysis/financials.py

Модуль расчёта финансовых коэффициентов на основе данных ОПУ и Баланса.
"""

from typing import Dict, Any, Optional
from core import utils  # предполагаем, что utils содержит to_float, stats, etc.

from infra.logger import get_logger
from infra.error_handler import safe_run


class FinancialsAnalyzer:
    """
    Рассчитывает ключевые финансовые коэффициенты:
    - ликвидность (current, quick)
    - рентабельность (gross margin, EBITDA margin, net margin)
    - финансовый рычаг (debt to equity)
    - возврат на капитал (ROE), возврат на активы (ROA) если возможно
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Расчёт финансовых коэффициентов", retries=2, base_delay=1.0)
    def analyze(self, opu: Dict[str, Any], bal: Dict[str, Any]) -> Dict[str, Any]:
        """
        :param opu: структура из parser_opu (values, metrics, insights)
        :param bal: структура из parser_balance (values, metrics, insights)
        :return: словарь с коэффициентами и текстовыми интерпретациями
        """
        vals = opu.get("values", {})
        metrics = opu.get("metrics", {})
        bal_vals = bal.get("values", {})
        bal_metrics = bal.get("metrics", {})

        # Получаем нужные величины
        revenue = utils.to_float(vals.get("revenue"))
        net_profit = utils.to_float(vals.get("net_profit"))
        ebitda = utils.to_float(metrics.get("ebitda"))
        capital = utils.to_float(bal_vals.get("capital"))
        noncurrent = utils.to_float(bal_vals.get("noncurrent_assets"))
        current_assets = utils.to_float(bal_vals.get("current_assets"))
        inventory = utils.to_float(bal_vals.get("inventory"))
        receivables = utils.to_float(bal_vals.get("receivables"))
        cash = utils.to_float(bal_vals.get("cash"))
        short_term_liabilities = utils.to_float(bal_vals.get("short_term_liabilities"))
        long_term_liabilities = utils.to_float(bal_vals.get("long_term_liabilities"))

        total_liabilities = None
        if short_term_liabilities is not None and long_term_liabilities is not None:
            total_liabilities = short_term_liabilities + long_term_liabilities

        # Расчёты коэффициентов
        coeffs: Dict[str, Optional[float]] = {}

        # Current Ratio
        if current_assets is not None and short_term_liabilities and short_term_liabilities != 0:
            coeffs["current_ratio"] = current_assets / short_term_liabilities
        else:
            coeffs["current_ratio"] = None

        # Quick Ratio = (Cash + Receivables) / Short-term liabilities (или (Current – Inventory) / STLiabilities)
        if short_term_liabilities and short_term_liabilities != 0:
            if cash is not None and receivables is not None:
                coeffs["quick_ratio"] = (cash + receivables) / short_term_liabilities
            elif current_assets is not None and inventory is not None:
                coeffs["quick_ratio"] = (current_assets - inventory) / short_term_liabilities
            else:
                coeffs["quick_ratio"] = None
        else:
            coeffs["quick_ratio"] = None

        # Debt-to-Equity
        if total_liabilities is not None and capital is not None and capital != 0:
            coeffs["debt_to_equity"] = total_liabilities / capital
        else:
            coeffs["debt_to_equity"] = None

        # Gross Margin (если revenue и cost of goods sold есть)
        cogs = utils.to_float(vals.get("cogs"))
        if revenue is not None and cogs is not None and revenue != 0:
            coeffs["gross_margin"] = (revenue - cogs) / revenue
        else:
            coeffs["gross_margin"] = None

        # EBITDA Margin
        if ebitda is not None and revenue is not None and revenue != 0:
            coeffs["ebitda_margin"] = ebitda / revenue
        else:
            coeffs["ebitda_margin"] = None

        # Net Profit Margin
        if net_profit is not None and revenue is not None and revenue != 0:
            coeffs["net_margin"] = net_profit / revenue
        else:
            coeffs["net_margin"] = None

        # ROE = Net Profit / Capital
        if net_profit is not None and capital is not None and capital != 0:
            coeffs["ROE"] = net_profit / capital
        else:
            coeffs["ROE"] = None

        # ROA = Net Profit / Total Assets (акт = noncurrent + current)
        total_assets = None
        if noncurrent is not None and current_assets is not None:
            total_assets = noncurrent + current_assets
        if net_profit is not None and total_assets and total_assets != 0:
            coeffs["ROA"] = net_profit / total_assets
        else:
            coeffs["ROA"] = None

        # Интерпретации
        insights = self._interpret(coeffs)

        return {"coeffs": coeffs, "insights": insights}

    def _interpret(self, coeffs: Dict[str, Optional[float]]) -> Dict[str, str]:
        """
        Генерация коротких аннотаций по коэффициентам
        """
        ins: Dict[str, str] = {}
        cr = coeffs.get("current_ratio")
        if cr is not None:
            ins["current_ratio"] = f"Текущая ликвидность = {cr:.2f}. " + ("Достаточно" if cr >= 1.5 else "Низкая, риск ликвидности")
        else:
            ins["current_ratio"] = "Не удалось рассчитать current_ratio"

        qr = coeffs.get("quick_ratio")
        if qr is not None:
            ins["quick_ratio"] = f"Быстрая ликвидность = {qr:.2f}. " + ("Ок" if qr >= 1 else "Может быть риск при низком qr")
        else:
            ins["quick_ratio"] = "Не удалось рассчитать quick_ratio"

        de = coeffs.get("debt_to_equity")
        if de is not None:
            ins["debt_to_equity"] = f"Соотношение долга к капиталу = {de:.2f}. " + ("Нормально" if de <= 2 else "Высокий уровень заемного капитала")
        else:
            ins["debt_to_equity"] = "Не удалось рассчитать debt_to_equity"

        gm = coeffs.get("gross_margin")
        if gm is not None:
            ins["gross_margin"] = f"Валовая маржа = {gm:.1%}. " + ("Хорошая" if gm >= 0.3 else "Низкая маржа")
        else:
            ins["gross_margin"] = "Не удалось рассчитать gross_margin"

        em = coeffs.get("ebitda_margin")
        if em is not None:
            ins["ebitda_margin"] = f"EBITDA-маржа = {em:.1%}. " + ("Норма" if em >= 0.15 else "Низкая операционная прибыль")
        else:
            ins["ebitda_margin"] = "Не удалось рассчитать ebitda_margin"

        nm = coeffs.get("net_margin")
        if nm is not None:
            ins["net_margin"] = f"Чистая маржа = {nm:.1%}. " + ("Положительный результат" if nm > 0 else "Убыток/риск")
        else:
            ins["net_margin"] = "Не удалось рассчитать net_margin"

        roe = coeffs.get("ROE")
        if roe is not None:
            ins["ROE"] = f"ROE = {roe:.1%}. " + ("Хороший доход на капитал" if roe >= 0.1 else "Низкая отдача")
        else:
            ins["ROE"] = "Не удалось рассчитать ROE"

        roa = coeffs.get("ROA")
        if roa is not None:
            ins["ROA"] = f"ROA = {roa:.1%}. " + ("Эффективно" if roa >= 0.05 else "Низкий возврат на активы")
        else:
            ins["ROA"] = "Не удалось рассчитать ROA"

        return ins
