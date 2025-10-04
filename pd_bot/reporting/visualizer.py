# -*- coding: utf-8 -*-
"""
reporting/visualizer.py
Построение графиков для отчёта PD-модели.
"""

import matplotlib.pyplot as plt
from typing import Dict, Any, List
import os
from infra.logger import get_logger
from infra.error_handler import safe_run


class Visualizer:
    """
    Строит графики:
    - cashflow vs payments
    - DSCR timeline
    - aging дебиторки
    - концентрация контрагентов
    - динамика остатков 51
    """

    def __init__(self, out_dir: str = "output/plots"):
        self.logger = get_logger()
        self.out_dir = out_dir
        os.makedirs(self.out_dir, exist_ok=True)

    @safe_run(stage="Визуализация", retries=1)
    def plot_cashflow_vs_payments(self, cashflow: Dict[str, Any], payments: List[Dict[str, Any]], filename="cashflow_vs_payments.png"):
        months = sorted(set(cashflow.get("by_month_in", {}).keys()) | set(cashflow.get("by_month_out", {}).keys()))
        inflow = [cashflow.get("by_month_in", {}).get(m, 0) for m in months]
        outflow = [cashflow.get("by_month_out", {}).get(m, 0) for m in months]
        pays = [p.get("amount", 0) for p in payments[:len(months)]]

        plt.figure(figsize=(10, 6))
        plt.plot(months, inflow, label="Cash-in", marker="o")
        plt.plot(months, outflow, label="Cash-out", marker="o")
        plt.bar(months, pays, alpha=0.5, label="Lease Payment")
        plt.axhline(0, color="black", linewidth=0.7)
        plt.legend()
        plt.title("Cashflow vs Payments")
        plt.xticks(rotation=45)
        plt.tight_layout()
        path = os.path.join(self.out_dir, filename)
        plt.savefig(path)
        plt.close()
        return path

    @safe_run(stage="Визуализация DSCR", retries=1)
    def plot_dscr(self, dscr_by_month: Dict[str, float], filename="dscr_timeline.png"):
        months = sorted(dscr_by_month.keys())
        values = [dscr_by_month[m] for m in months]

        plt.figure(figsize=(10, 5))
        plt.plot(months, values, marker="o", color="blue")
        plt.axhline(1, color="red", linestyle="--", label="DSCR = 1")
        plt.title("DSCR Timeline")
        plt.ylabel("DSCR")
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        path = os.path.join(self.out_dir, filename)
        plt.savefig(path)
        plt.close()
        return path

    @safe_run(stage="Визуализация Aging дебиторки", retries=1)
    def plot_aging(self, aging: Dict[str, float], filename="receivables_aging.png"):
        labels = list(aging.keys())
        values = list(aging.values())

        plt.figure(figsize=(6, 6))
        plt.bar(labels, values, color="orange")
        plt.title("Aging дебиторки")
        plt.ylabel("Сумма")
        plt.tight_layout()
        path = os.path.join(self.out_dir, filename)
        plt.savefig(path)
        plt.close()
        return path

    @safe_run(stage="Визуализация концентрации", retries=1)
    def plot_concentration(self, top_list: List[Dict[str, Any]], filename="concentration.png"):
        labels = [item["name"] for item in top_list]
        sizes = [item["amount"] for item in top_list]

        plt.figure(figsize=(6, 6))
        plt.pie(sizes, labels=labels, autopct="%1.1f%%")
        plt.title("Концентрация контрагентов")
        path = os.path.join(self.out_dir, filename)
        plt.savefig(path)
        plt.close()
        return path

    @safe_run(stage="Визуализация остатков", retries=1)
    def plot_balances(self, balances: Dict[str, float], filename="balances.png"):
        months = sorted(balances.keys())
        values = [balances[m] for m in months]

        plt.figure(figsize=(10, 5))
        plt.plot(months, values, marker="o")
        plt.title("Динамика остатков по счёту 51")
        plt.ylabel("Остаток")
        plt.xticks(rotation=45)
        plt.tight_layout()
        path = os.path.join(self.out_dir, filename)
        plt.savefig(path)
        plt.close()
        return path
