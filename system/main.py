# -*- coding: utf-8 -*-
"""
system/main.py
Главный пайплайн PD-модели.
"""

import os
import glob

from infra.logger import get_logger
from core.document_loader import DocumentLoader
from core.parser_opu import OPUParser
from core.parser_balance import BalanceParser
from core.parser_51 import Card51Parser
from core.parser_osv import OSVParser
from core.parser_kp import KPParser

from analysis.financials import FinancialsAnalyzer
from analysis.balance import BalanceAnalyzer
from analysis.cashflow import CashflowAnalyzer
from analysis.receivables import ReceivablesAnalyzer
from analysis.payables import PayablesAnalyzer
from analysis.deal import DealAnalyzer
from analysis.retro import RetroSimulator
from analysis.scoring import ScoringModel

from reporting.formatter import ReportFormatter
from reporting.visualizer import Visualizer
from reporting.exporter import ReportExporter

from system import config


logger = get_logger()


def run_pipeline(input_dir: str = config.INPUT_DIR):
    logger.info("=== Старт PD-пайплайна ===")

    loader = DocumentLoader()

    # Парсеры
    opu_parser = OPUParser()
    bal_parser = BalanceParser()
    card51_parser = Card51Parser()
    osv_parser = OSVParser()
    kp_parser = KPParser()

    # Аналитика
    fin_an = FinancialsAnalyzer()
    bal_an = BalanceAnalyzer()
    cash_an = CashflowAnalyzer()
    recv_an = ReceivablesAnalyzer()
    pay_an = PayablesAnalyzer()
    deal_an = DealAnalyzer()
    retro_an = RetroSimulator()
    scoring = ScoringModel()

    # Отчёт
    formatter = ReportFormatter()
    viz = Visualizer()
    exporter = ReportExporter()

    results = {}

    # ---------- Загрузка документов ----------
    files = glob.glob(os.path.join(input_dir, "*"))
    logger.info(f"Найдено файлов: {len(files)}")

    for f in files:
        doc = loader.load(f)
        doc_type = doc.get("doc_type")
        raw = doc.get("raw_data")

        if doc_type == "OPU":
            results["opu"] = opu_parser.parse(raw)
        elif doc_type == "BALANCE":
            results["balance_raw"] = bal_parser.parse(raw)
        elif doc_type == "CARD51":
            results["card51"] = card51_parser.parse(raw)
        elif doc_type == "OSV60":
            results["osv60"] = osv_parser.parse(raw, account_type="60")
        elif doc_type == "OSV62":
            results["osv62"] = osv_parser.parse(raw, account_type="62")
        elif doc_type == "KP":
            results["kp"] = kp_parser.parse(f)

    # ---------- Анализ ----------
    if "opu" in results and "balance_raw" in results:
        results["financials"] = fin_an.analyze(results["opu"], results["balance_raw"])
        results["balance"] = bal_an.analyze(results["balance_raw"])

    if "card51" in results:
        results["cashflow"] = cash_an.analyze(results["card51"], lease_payment=results.get("kp", {}).get("metrics", {}).get("avg_payment", 0))

    if "osv62" in results:
        results["receivables"] = recv_an.analyze(results["osv62"])

    if "osv60" in results:
        results["payables"] = pay_an.analyze(results["osv60"])

    if "kp" in results and "opu" in results and "balance_raw" in results and "card51" in results:
        results["deal"] = deal_an.analyze(results["kp"], results["opu"], results["balance_raw"], results["card51"])

    if "card51" in results and "kp" in results:
        results["retro"] = retro_an.simulate(results["card51"], results["kp"])

    results["scoring"] = scoring.score(results)

    # ---------- Отчёт ----------
    md_report = formatter.format_report(results)

    images = []
    if "cashflow" in results and "kp" in results:
        images.append(viz.plot_cashflow_vs_payments(results["cashflow"]["monthly"], results["kp"].get("schedule", {}).get("regular", [])))
    if "cashflow" in results and results["cashflow"]["metrics"].get("DSCR_by_month"):
        images.append(viz.plot_dscr(results["cashflow"]["metrics"]["DSCR_by_month"]))
    if "receivables" in results:
        images.append(viz.plot_aging(results["receivables"]["aging"]))
        images.append(viz.plot_concentration(results["receivables"]["top_debtors"].get("top", [])))
    if "payables" in results:
        images.append(viz.plot_concentration(results["payables"]["top_suppliers"].get("top", [])))
    if "card51" in results:
        images.append(viz.plot_balances(results["card51"]["balances"]["summary"]["by_month_end"]))

    exporter.export_markdown(md_report, "report.md")
    exporter.export_pdf(md_report, images, "report.pdf")
    exporter.export_txt(md_report, "report.txt")

    logger.info("=== Отчёт успешно сформирован ===")
    print(f"\nОтчёт сформирован:\n- Markdown: output/reports/report.md\n- PDF: output/reports/report.pdf\n- TXT: output/reports/report.txt\n")


if __name__ == "__main__":
    run_pipeline()
