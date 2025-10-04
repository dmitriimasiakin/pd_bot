# -*- coding: utf-8 -*-
"""
analysis/scoring.py
Финальный скоринг PD-модели: объединение всех коэффициентов и расчёт риска.
Расширенная версия с весами, объяснениями и декомпозицией PD.
"""

from typing import Dict, Any
from infra.logger import get_logger
from infra.error_handler import safe_run


class ScoringModel:
    """
    Считает итоговый скоринг PD:
    - собирает коэффициенты из всех анализов
    - применяет пороговую матрицу с весами
    - формирует детальные объяснения
    - выдаёт декомпозицию PD (по блокам)
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Финальный скоринг PD", retries=2, base_delay=1.0)
    def score(self, results: Dict[str, Any]) -> Dict[str, Any]:
        fin = results.get("financials", {}).get("coeffs", {})
        bal = results.get("balance", {})
        cash = results.get("cashflow", {}).get("metrics", {})
        recv = results.get("receivables", {}).get("metrics", {})
        pay = results.get("payables", {}).get("metrics", {})
        retro = results.get("retro", {}).get("metrics", {})

        scorecard = {}
        explanations = {}

        # Вспомогательная функция
        def score_metric(value, thresholds, name, weight=1, fmt="{:.2f}"):
            if value is None:
                explanations[name] = f"{name}: данные отсутствуют → 0 баллов"
                return 0, 0
            for rng, pts, desc in thresholds:
                if rng(value):
                    explanations[name] = f"{name} = {fmt.format(value)} → {desc} → {pts} балл(ов), вес {weight}"
                    return pts * weight, pts
            explanations[name] = f"{name} = {fmt.format(value)} → вне диапазона → 0 баллов"
            return 0, 0

        # ---------- Основные метрики ----------

        # DSCR (критичный показатель)
        sc, raw = score_metric(cash.get("avg_DSCR"), [
            (lambda v: v < 1, 0, "DSCR < 1, покрытие долга отсутствует ⚠"),
            (lambda v: 1 <= v < 1.2, 1, "DSCR = слабое покрытие"),
            (lambda v: v >= 1.2, 2, "DSCR = устойчивое покрытие"),
        ], "DSCR", weight=2)
        scorecard["DSCR"] = (sc, raw)

        # Retro PD
        sc, raw = score_metric(retro.get("prob_default"), [
            (lambda v: v > 0.5, 0, "Вероятность дефолта > 50% ⚠"),
            (lambda v: 0.2 <= v <= 0.5, 1, "Средняя вероятность дефолта"),
            (lambda v: v < 0.2, 2, "Низкая вероятность дефолта"),
        ], "Retro PD", weight=2, fmt="{:.1%}")
        scorecard["Retro PD"] = (sc, raw)

        # Liquidity
        sc, raw = score_metric(fin.get("current_ratio"), [
            (lambda v: v < 1, 0, "Current ratio < 1 ⚠"),
            (lambda v: 1 <= v < 1.5, 1, "Current ratio среднее"),
            (lambda v: v >= 1.5, 2, "Current ratio устойчивое"),
        ], "Current Ratio", weight=1.5)
        scorecard["Current Ratio"] = (sc, raw)

        sc, raw = score_metric(bal.get("liquidity", {}).get("absolute"), [
            (lambda v: v < 0.2, 0, "Абсолютная ликвидность < 0.2 ⚠"),
            (lambda v: 0.2 <= v < 0.5, 1, "Абсолютная ликвидность средняя"),
            (lambda v: v >= 0.5, 2, "Абсолютная ликвидность высокая"),
        ], "Absolute Liquidity", weight=1)
        scorecard["Absolute Liquidity"] = (sc, raw)

        # Structure
        sc, raw = score_metric(bal.get("stability", {}).get("autonomy"), [
            (lambda v: v < 0.2, 0, "Коэф. автономии < 0.2 ⚠"),
            (lambda v: 0.2 <= v < 0.4, 1, "Автономия средняя"),
            (lambda v: v >= 0.4, 2, "Автономия высокая"),
        ], "Equity Ratio", weight=1.5, fmt="{:.1%}")
        scorecard["Equity Ratio"] = (sc, raw)

        # Receivables
        sc, raw = score_metric(recv.get("DSO"), [
            (lambda v: v > 90, 0, "DSO > 90 дней ⚠"),
            (lambda v: 60 <= v <= 90, 1, "DSO умеренный"),
            (lambda v: v < 60, 2, "DSO хороший"),
        ], "DSO", weight=1.5)
        scorecard["DSO"] = (sc, raw)

        # Payables
        sc, raw = score_metric(pay.get("DPO"), [
            (lambda v: v > 120, 0, "DPO > 120 дней ⚠"),
            (lambda v: 60 <= v <= 120, 1, "DPO средний"),
            (lambda v: v < 60, 2, "DPO короткий"),
        ], "DPO", weight=1.5)
        scorecard["DPO"] = (sc, raw)

        # Profitability
        sc, raw = score_metric(fin.get("gross_margin"), [
            (lambda v: v < 0.2, 0, "Gross margin низкая ⚠"),
            (lambda v: 0.2 <= v < 0.3, 1, "Gross margin средняя"),
            (lambda v: v >= 0.3, 2, "Gross margin высокая"),
        ], "Gross Margin", weight=1, fmt="{:.1%}")
        scorecard["Gross Margin"] = (sc, raw)

        sc, raw = score_metric(fin.get("ebitda_margin"), [
            (lambda v: v < 0.1, 0, "EBITDA margin низкая ⚠"),
            (lambda v: 0.1 <= v < 0.15, 1, "EBITDA margin средняя"),
            (lambda v: v >= 0.15, 2, "EBITDA margin высокая"),
        ], "EBITDA Margin", weight=1, fmt="{:.1%}")
        scorecard["EBITDA Margin"] = (sc, raw)

        sc, raw = score_metric(fin.get("net_margin"), [
            (lambda v: v <= 0, 0, "Убыток ⚠"),
            (lambda v: 0 < v < 0.1, 1, "Чистая маржа низкая"),
            (lambda v: v >= 0.1, 2, "Чистая маржа хорошая"),
        ], "Net Margin", weight=1, fmt="{:.1%}")
        scorecard["Net Margin"] = (sc, raw)

        sc, raw = score_metric(fin.get("ROE"), [
            (lambda v: v < 0.05, 0, "ROE < 5% ⚠"),
            (lambda v: 0.05 <= v < 0.1, 1, "ROE средний"),
            (lambda v: v >= 0.1, 2, "ROE высокий"),
        ], "ROE", weight=1, fmt="{:.1%}")
        scorecard["ROE"] = (sc, raw)

        sc, raw = score_metric(fin.get("ROA"), [
            (lambda v: v < 0.02, 0, "ROA < 2% ⚠"),
            (lambda v: 0.02 <= v < 0.05, 1, "ROA средний"),
            (lambda v: v >= 0.05, 2, "ROA высокий"),
        ], "ROA", weight=1, fmt="{:.1%}")
        scorecard["ROA"] = (sc, raw)

        # Burn-rate
        sc, raw = score_metric(cash.get("burn_rate_months"), [
            (lambda v: v < 3, 0, "Burn-rate < 3 мес ⚠"),
            (lambda v: 3 <= v < 6, 1, "Burn-rate средний"),
            (lambda v: v >= 6, 2, "Burn-rate устойчивый"),
        ], "Burn-rate", weight=1)
        scorecard["Burn-rate"] = (sc, raw)

        # ---------- Итог ----------

        total_score = sum(sc for sc, raw in scorecard.values())
        max_score = sum(2 * (2 if "DSCR" in k or "Retro PD" in k else 1) for k in scorecard)  # веса
        pd = 1 - (total_score / max_score) if max_score > 0 else None

        if total_score <= max_score * 0.33:
            risk_class = "Высокий риск"
        elif total_score <= max_score * 0.66:
            risk_class = "Средний риск"
        else:
            risk_class = "Низкий риск"

        return {
            "scorecard": {k: {"weighted_score": sc, "raw_score": raw} for k, (sc, raw) in scorecard.items()},
            "explanations": explanations,
            "total_score": total_score,
            "max_score": max_score,
            "PD": pd,
            "risk_class": risk_class,
        }
