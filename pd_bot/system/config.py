# -*- coding: utf-8 -*-
"""
system/config.py
Конфигурация проекта PD-модели.
"""

import os

# ---------- Пути ----------

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
REPORTS_DIR = os.path.join(OUTPUT_DIR, "reports")
PLOTS_DIR = os.path.join(OUTPUT_DIR, "plots")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Создаём папки при необходимости
for path in [INPUT_DIR, OUTPUT_DIR, REPORTS_DIR, PLOTS_DIR, LOG_DIR]:
    os.makedirs(path, exist_ok=True)


# ---------- Логирование ----------

LOG_FILE = os.path.join(LOG_DIR, "pd_model.log")
LOG_LEVEL = "INFO"  # можно поменять на DEBUG


# ---------- Пороговые значения для скоринга ----------

THRESHOLDS = {
    "DSCR": {"low": 1.0, "medium": 1.2},
    "Current Ratio": {"low": 1.0, "medium": 1.5},
    "Equity Ratio": {"low": 0.2, "medium": 0.4},
    "Absolute Liquidity": {"low": 0.2, "medium": 0.5},
    "DSO": {"high": 90, "medium": 60},   # дни
    "DPO": {"high": 120, "medium": 60},  # дни
    "Gross Margin": {"low": 0.2, "medium": 0.3},
    "EBITDA Margin": {"low": 0.1, "medium": 0.15},
    "Net Margin": {"low": 0.0, "medium": 0.1},
    "ROE": {"low": 0.05, "medium": 0.1},
    "ROA": {"low": 0.02, "medium": 0.05},
    "Burn-rate": {"low": 3, "medium": 6},  # месяцев
    "Retro PD": {"high": 0.5, "medium": 0.2},
    "Concentration": {"high": 0.5, "medium": 0.3},
}


# ---------- Настройки отчётов ----------

REPORT_SETTINGS = {
    "page_size": "A4",
    "font": "Helvetica",
    "title_size": 16,
    "heading_size": 14,
    "normal_size": 10,
}


# ---------- Общие параметры ----------

MAX_RETRIES = 3
RETRY_DELAY = 1.0
TIMEOUT = 30  # секунд
