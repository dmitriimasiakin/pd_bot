# -*- coding: utf-8 -*-
"""
core/parser_balance.py
Парсер бухгалтерского баланса (Форма 1).
"""

import pandas as pd
from typing import Dict, Any, Union

from infra.logger import get_logger
from infra.error_handler import safe_run


class BalanceParser:
    """
    Разбирает баланс (форма 1),
    рассчитывает коэффициенты ликвидности и устойчивости.
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Парсинг Баланса", retries=2, base_delay=1.0)
    def parse(self, raw_data: Union[pd.DataFrame, str]) -> Dict[str, Any]:
        """
        Разбор документа (DataFrame или текст).
        """
        lines = self._extract_text(raw_data)

        values = {
            "noncurrent_assets": self._find_value(lines, ["внеоборотные активы"]),
            "current_assets": self._find_value(lines, ["оборотные активы"]),
            "inventory": self._find_value(lines, ["запасы"]),
            "receivables": self._find_value(lines, ["дебиторская задолженность"]),
            "cash": self._find_value(lines, ["денежные средства"]),
            "capital": self._find_value(lines, ["капитал", "резервы", "собственный капитал"]),
            "long_term_liabilities": self._find_value(lines, ["долгосрочные обязательства"]),
            "short_term_liabilities": self._find_value(lines, ["краткосрочные обязательства"]),
        }

        # Агрегаты
        assets = None
        if values["noncurrent_assets"] is not None and values["current_assets"] is not None:
            assets = values["noncurrent_assets"] + values["current_assets"]

        liabilities = None
        if values["long_term_liabilities"] is not None and values["short_term_liabilities"] is not None:
            liabilities = values["long_term_liabilities"] + values["short_term_liabilities"]

        # Метрики
        metrics = self._calculate_metrics(values, assets, liabilities)

        # Выводы
        insights = self._generate_insights(metrics)

        return {"values": values, "metrics": metrics, "insights": insights}

    def _extract_text(self, raw: Union[pd.DataFrame, str]):
        """Объединяем таблицу/текст в список строк"""
        if isinstance(raw, pd.DataFrame):
            lines = raw.fillna("").astype(str).agg(" ".join, axis=1).tolist()
        else:
            lines = raw.splitlines()
        return [l.strip().lower() for l in lines if l.strip()]

    def _find_value(self, lines, keywords):
        """Поиск числа рядом с ключевыми словами"""
        import re
        for line in lines:
            if any(k in line for k in keywords):
                numbers = re.findall(r"-?\d+(?:[.,]\d+)?", line.replace(" ", ""))
                if numbers:
                    try:
                        return float(numbers[-1].replace(",", "."))
                    except Exception:
                        continue
        return None

    def _calculate_metrics(self, values, assets, liabilities) -> Dict[str, Any]:
        """Коэффициенты ликвидности и устойчивости"""
        current_assets = values.get("current_assets") or 0
        inventory = values.get("inventory") or 0
        receivables = values.get("receivables") or 0
        cash = values.get("cash") or 0
        short_term_liabilities = values.get("short_term_liabilities") or 0
        capital = values.get("capital") or 0

        metrics = {}

        # Текущая ликвидность
        if short_term_liabilities > 0:
            metrics["current_ratio"] = current_assets / short_term_liabilities
        else:
            metrics["current_ratio"] = None

        # Быстрая ликвидность
        if short_term_liabilities > 0:
            metrics["quick_ratio"] = (receivables + cash) / short_term_liabilities
        else:
            metrics["quick_ratio"] = None

        # Автономия (капитал / активы)
        if assets and assets > 0:
            metrics["equity_ratio"] = capital / assets
        else:
            metrics["equity_ratio"] = None

        # Заемный/собственный капитал
        if capital > 0 and liabilities:
            metrics["debt_to_equity"] = liabilities / capital
        else:
            metrics["debt_to_equity"] = None

        return metrics

    def _generate_insights(self, metrics: Dict[str, Any]):
        """Комментарии к метрикам"""
        insights = {}

        cr = metrics.get("current_ratio")
        if cr is not None:
            insights["current_ratio"] = f"Текущая ликвидность {cr:.2f}. {'Норма' if cr >= 1.5 else 'Ниже нормы'}."
        else:
            insights["current_ratio"] = "Не удалось рассчитать текущую ликвидность."

        qr = metrics.get("quick_ratio")
        if qr is not None:
            insights["quick_ratio"] = f"Быстрая ликвидность {qr:.2f}. {'Приемлемо' if qr >= 1 else 'Ниже нормы'}."
        else:
            insights["quick_ratio"] = "Не удалось рассчитать быструю ликвидность."

        er = metrics.get("equity_ratio")
        if er is not None:
            insights["equity_ratio"] = f"Автономия {er:.1%}. {'Устойчиво' if er > 0.4 else 'Высокая зависимость от долгов'}."
        else:
            insights["equity_ratio"] = "Не удалось рассчитать коэффициент автономии."

        de = metrics.get("debt_to_equity")
        if de is not None:
            insights["debt_to_equity"] = f"Заемный капитал к собственному {de:.2f}. {'Рискованно' if de > 2 else 'В норме'}."
        else:
            insights["debt_to_equity"] = "Не удалось рассчитать D/E."

        return insights
