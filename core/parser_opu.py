# -*- coding: utf-8 -*-
"""
core/parser_opu.py
Парсер отчёта о прибылях и убытках (ОПУ, форма 2).
"""

import pandas as pd
from typing import Dict, Any, Union

from infra.logger import get_logger
from infra.error_handler import safe_run


class OPUParser:
    """
    Разбирает ОПУ (форма 2), извлекает ключевые строки,
    рассчитывает маржинальности и даёт выводы.
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Парсинг ОПУ", retries=2, base_delay=1.0)
    def parse(self, raw_data: Union[pd.DataFrame, str]) -> Dict[str, Any]:
        """
        Разбор документа (DataFrame или текст)
        """
        text_data = self._extract_text(raw_data)

        values = {
            "revenue": self._find_value(text_data, ["выручка"]),
            "cogs": self._find_value(text_data, ["себестоимость"]),
            "gross_profit": self._find_value(text_data, ["валовая прибыль"]),
            "commercial_expenses": self._find_value(text_data, ["коммерческие расходы"]),
            "admin_expenses": self._find_value(text_data, ["управленческие расходы"]),
            "interest_expenses": self._find_value(text_data, ["проценты к уплате"]),
            "other_income": self._find_value(text_data, ["прочие доходы"]),
            "other_expenses": self._find_value(text_data, ["прочие расходы"]),
            "profit_before_tax": self._find_value(text_data, ["прибыль до налогообложения"]),
            "net_profit": self._find_value(text_data, ["чистая прибыль"]),
        }

        # Расчёт derived-метрик
        metrics = self._calculate_metrics(values)

        # Формируем выводы
        insights = self._generate_insights(values, metrics)

        return {"values": values, "metrics": metrics, "insights": insights}

    def _extract_text(self, raw: Union[pd.DataFrame, str]):
        """Объединяем таблицу/текст в список строк"""
        if isinstance(raw, pd.DataFrame):
            lines = raw.fillna("").astype(str).agg(" ".join, axis=1).tolist()
        else:
            lines = raw.splitlines()
        return [l.strip().lower() for l in lines if l.strip()]

    def _find_value(self, lines, keywords):
        """Поиск первой цифры рядом с ключевым словом"""
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

    def _calculate_metrics(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """Рассчёт EBITDA, EBIT, маржинальностей"""
        revenue = values.get("revenue") or 0
        cogs = values.get("cogs") or 0
        gp = values.get("gross_profit") or (revenue - cogs if revenue and cogs else None)

        ebitda = gp
        if values.get("commercial_expenses") is not None:
            ebitda -= values["commercial_expenses"]
        if values.get("admin_expenses") is not None:
            ebitda -= values["admin_expenses"]

        ebit = ebitda
        if values.get("other_income") is not None:
            ebit += values["other_income"]
        if values.get("other_expenses") is not None:
            ebit -= values["other_expenses"]

        net_profit = values.get("net_profit")

        metrics = {
            "gross_profit": gp,
            "ebitda": ebitda,
            "ebit": ebit,
            "gross_margin": (gp / revenue) if revenue else None,
            "ebitda_margin": (ebitda / revenue) if revenue else None,
            "net_margin": (net_profit / revenue) if revenue and net_profit else None,
        }
        return metrics

    def _generate_insights(self, values: Dict[str, Any], metrics: Dict[str, Any]):
        """Генерация комментариев по каждому показателю"""
        insights = {}

        if values.get("revenue") is not None:
            rev = values["revenue"]
            insights["revenue"] = f"Выручка составила {rev:,.0f} руб. Это база для анализа."
        else:
            insights["revenue"] = "Выручка не найдена в отчёте."

        if metrics.get("gross_margin") is not None:
            gm = metrics["gross_margin"]
            insights["gross_margin"] = f"Валовая маржа {gm:.1%}. {'Хорошо' if gm > 0.3 else 'Слабая маржа'}."
        else:
            insights["gross_margin"] = "Валовая маржа не рассчитана."

        if metrics.get("ebitda_margin") is not None:
            em = metrics["ebitda_margin"]
            insights["ebitda_margin"] = f"EBITDA-маржа {em:.1%}. {'Устойчивый бизнес' if em > 0.15 else 'Есть риски по операционным расходам'}."
        else:
            insights["ebitda_margin"] = "EBITDA-маржа не рассчитана."

        if metrics.get("net_margin") is not None:
            nm = metrics["net_margin"]
            insights["net_margin"] = f"Чистая маржа {nm:.1%}. {'Положительный результат' if nm > 0 else 'Убытки'}."
        else:
            insights["net_margin"] = "Чистая маржа не рассчитана."

        return insights
