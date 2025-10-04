# -*- coding: utf-8 -*-
"""
analysis/balance.py
Углублённый анализ бухгалтерского баланса (Форма 1).
"""

from typing import Dict, Any, Optional
from infra.logger import get_logger
from infra.error_handler import safe_run
from core import utils


class BalanceAnalyzer:
    """
    Углублённый анализ баланса:
    - структура активов и пассивов
    - коэффициенты ликвидности (абсолютная, промежуточная, общая)
    - коэффициенты устойчивости (автономия, зависимость, манёвренность)
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Анализ баланса", retries=2, base_delay=1.0)
    def analyze(self, bal: Dict[str, Any]) -> Dict[str, Any]:
        vals = bal.get("values", {})

        noncurrent = utils.to_float(vals.get("noncurrent_assets"))
        current_assets = utils.to_float(vals.get("current_assets"))
        inventory = utils.to_float(vals.get("inventory"))
        receivables = utils.to_float(vals.get("receivables"))
        cash = utils.to_float(vals.get("cash"))
        capital = utils.to_float(vals.get("capital"))
        st_liab = utils.to_float(vals.get("short_term_liabilities"))
        lt_liab = utils.to_float(vals.get("long_term_liabilities"))

        total_assets = None
        if noncurrent is not None and current_assets is not None:
            total_assets = noncurrent + current_assets

        total_liabilities = None
        if st_liab is not None and lt_liab is not None:
            total_liabilities = st_liab + lt_liab

        # ----------- Структура -----------

        structure = {
            "noncurrent_share": (noncurrent / total_assets) if total_assets else None,
            "current_share": (current_assets / total_assets) if total_assets else None,
            "equity_share": (capital / total_assets) if total_assets and capital is not None else None,
            "liabilities_share": (total_liabilities / total_assets) if total_assets and total_liabilities is not None else None,
            "short_term_liab_share": (st_liab / total_liabilities) if total_liabilities else None,
        }

        # ----------- Ликвидность -----------

        liquidity = {
            "absolute": (cash / st_liab) if cash is not None and st_liab else None,
            "intermediate": ((cash or 0) + (receivables or 0)) / st_liab if st_liab else None,
            "current": (current_assets / st_liab) if current_assets and st_liab else None,
        }

        # ----------- Устойчивость -----------

        stability = {
            "autonomy": (capital / total_assets) if capital and total_assets else None,
            "dependency": (total_liabilities / total_assets) if total_liabilities and total_assets else None,
            "maneuverability": ((capital - noncurrent) / capital) if capital and noncurrent is not None else None,
        }

        insights = self._generate_insights(structure, liquidity, stability)

        return {"structure": structure, "liquidity": liquidity, "stability": stability, "insights": insights}

    def _generate_insights(self, structure, liquidity, stability) -> Dict[str, str]:
        ins: Dict[str, str] = {}

        if structure.get("equity_share") is not None:
            val = structure["equity_share"]
            ins["equity_share"] = f"Доля капитала в активах {val:.1%}. " + ("Финансово устойчиво" if val >= 0.5 else "Зависимость от заёмных средств")

        if liquidity.get("absolute") is not None:
            val = liquidity["absolute"]
            ins["absolute"] = f"Абсолютная ликвидность = {val:.2f}. " + ("Ок (>0.2)" if val >= 0.2 else "Ниже нормы")

        if liquidity.get("intermediate") is not None:
            val = liquidity["intermediate"]
            ins["intermediate"] = f"Промежуточная ликвидность = {val:.2f}. " + ("Приемлемо (>0.7)" if val >= 0.7 else "Слабая")

        if stability.get("autonomy") is not None:
            val = stability["autonomy"]
            ins["autonomy"] = f"Коэф. автономии = {val:.2f}. " + ("Норма (>0.4)" if val >= 0.4 else "Низкая независимость")

        if stability.get("maneuverability") is not None:
            val = stability["maneuverability"]
            ins["maneuverability"] = f"Манёвренность капитала = {val:.2f}. " + ("Гибкая структура" if val > 0 else "Капитал закреплён во внеоборотных активах")

        return ins
