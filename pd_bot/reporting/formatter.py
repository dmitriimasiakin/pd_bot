# -*- coding: utf-8 -*-
"""
reporting/formatter.py
Генерация текстового отчёта (Markdown) по результатам PD-модели.
"""

from typing import Dict, Any, List
from infra.logger import get_logger
from infra.error_handler import safe_run


class ReportFormatter:
    """
    Формирует текстовый отчёт в Markdown:
    - собирает результаты всех анализов
    - форматирует таблицы и блоки
    - готовит к экспорту в PDF
    """

    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Формирование отчёта", retries=2, base_delay=1.0)
    def format_report(self, results: Dict[str, Any]) -> str:
        md = []

        # ---------- Введение ----------
        deal_params = results.get("deal", {}).get("deal_params", {})
        md.append("# 📊 Отчёт по анализу сделки\n")
        md.append("## Введение\n")
        md.append(f"- **Предмет лизинга**: {deal_params.get('lease_subject', 'не указано')}")
        md.append(f"- **Срок**: {deal_params.get('term_months', '—')} мес.")
        md.append(f"- **Аванс**: {deal_params.get('advance_payment', '—')} руб.\n")

        # ---------- Финансовые коэффициенты ----------
        fin = results.get("financials", {}).get("coeffs", {})
        md.append("## 💵 Финансовые коэффициенты\n")
        for k, v in fin.items():
            md.append(f"- {k}: {v:.2f}" if v is not None else f"- {k}: —")

        # ---------- Ликвидность и устойчивость ----------
        bal = results.get("balance", {})
        md.append("\n## 💧 Ликвидность и устойчивость\n")
        for k, v in {**bal.get("liquidity", {}), **bal.get("stability", {})}.items():
            md.append(f"- {k}: {v:.2f}" if v is not None else f"- {k}: —")

        # ---------- Денежные потоки ----------
        cash = results.get("cashflow", {})
        md.append("\n## 🔄 Денежные потоки (51 счёт)\n")
        metrics = cash.get("metrics", {})
        for k, v in metrics.items():
            if isinstance(v, dict):
                continue
            md.append(f"- {k}: {v:.2f}" if v is not None else f"- {k}: —")

        # ---------- Дебиторка ----------
        recv = results.get("receivables", {})
        md.append("\n## 📥 Дебиторская задолженность (ОСВ 62)\n")
        for k, v in recv.get("metrics", {}).items():
            md.append(f"- {k}: {v:.2f}" if v is not None else f"- {k}: —")

        # ---------- Кредиторка ----------
        pay = results.get("payables", {})
        md.append("\n## 📤 Кредиторская задолженность (ОСВ 60)\n")
        for k, v in pay.get("metrics", {}).items():
            md.append(f"- {k}: {v:.2f}" if v is not None else f"- {k}: —")

        # ---------- Сделка ----------
        deal = results.get("deal", {})
        md.append("\n## 📑 Сделка (КП)\n")
        for k, v in deal.get("payment_analysis", {}).items():
            md.append(f"- {k}: {v}" if v is not None else f"- {k}: —")

        # ---------- Ретро-симуляция ----------
        retro = results.get("retro", {}).get("metrics", {})
        md.append("\n## ⏳ Ретро-симуляция платежей\n")
        for k, v in retro.items():
            md.append(f"- {k}: {v}" if v is not None else f"- {k}: —")

        # ---------- Итоговый скоринг ----------
        score = results.get("scoring", {})
        md.append("\n## 🧮 Итоговый скоринг PD\n")
        md.append(f"- **Total Score**: {score.get('total_score', '—')} / {score.get('max_score', '—')}")
        md.append(f"- **PD (вероятность дефолта)**: {score.get('PD', '—'):.1%}" if score.get("PD") is not None else "- PD: —")
        md.append(f"- **Класс риска**: {score.get('risk_class', '—')}\n")

        # ---------- Заключение ----------
        md.append("## 📉 Заключение\n")
        md.append("Модель выявила ключевые риски и рассчитала вероятность дефолта. Подробные графики и таблицы см. в визуализации.\n")

        return "\n".join(md)
