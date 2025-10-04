# -*- coding: utf-8 -*-
"""
core/parser_kp.py
Парсер КП (коммерческого предложения) из PDF.
"""

import re
import pdfplumber
from typing import Dict, Any, List, Optional

from infra.logger import get_logger
from infra.error_handler import safe_run


class KPParser:
    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Парсинг КП", retries=2, base_delay=1.0, backoff=2.0, default={})
    def parse(self, filepath: str) -> Dict[str, Any]:
        """
        Разбор PDF-файла КП.
        :param filepath: путь к PDF
        :return: структура с параметрами, графиками и метриками
        """
        text_lines = self._extract_text(filepath)

        params = self._extract_params(text_lines)
        schedule = {
            "regular": self._extract_schedule(text_lines, section="ежемесяч"),
            "early_buyout": self._extract_schedule(text_lines, section="досроч"),
            "invoices": self._extract_schedule(text_lines, section="счет"),
        }
        metrics = self._calculate_metrics(params, schedule)

        return {"params": params, "schedule": schedule, "metrics": metrics}

    def _extract_text(self, filepath: str) -> List[str]:
        """Чтение PDF построчно"""
        lines = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                txt = page.extract_text() or ""
                for l in txt.splitlines():
                    lines.append(l.strip().lower())
        return [l for l in lines if l]

    def _extract_params(self, lines: List[str]) -> Dict[str, Any]:
        """Извлечение параметров сделки"""
        params = {}

        def find_num(patterns: List[str]) -> Optional[float]:
            for l in lines:
                if any(p in l for p in patterns):
                    nums = re.findall(r"\d[\d\s.,]+", l)
                    if nums:
                        return float(nums[-1].replace(" ", "").replace(",", "."))
            return None

        def find_text(patterns: List[str]) -> Optional[str]:
            for l in lines:
                if any(p in l for p in patterns):
                    return l
            return None

        params["term_months"] = find_num(["срок", "месяц"])
        params["advance_payment"] = find_num(["аванс"])
        params["lease_subject"] = find_text(["предмет", "автомоб", "техника"])
        params["price"] = find_num(["цена", "стоимость предмета"])
        params["total_cost"] = find_num(["стоимость лизинг", "сумма договора"])
        params["commission"] = find_num(["комисси"])
        params["subsidy"] = find_num(["субсиди"])
        params["nds"] = find_num(["ндс"])
        return params

    def _extract_schedule(self, lines: List[str], section: str) -> List[Dict[str, Any]]:
        """Извлечение графика (ежемесячные платежи, досрочный выкуп, счета-фактуры)"""
        rows = []
        capture = False
        for l in lines:
            if section in l:
                capture = True
                continue
            if capture:
                if re.match(r"^\d+\s", l):  # строка начинается с номера периода
                    parts = l.split()
                    if len(parts) >= 2:
                        period = parts[0]
                        try:
                            amount = float(parts[1].replace(" ", "").replace(",", "."))
                        except Exception:
                            amount = None
                        rows.append({"period": period, "amount": amount, "raw": l})
                else:
                    if rows:
                        break
        return rows

    def _calculate_metrics(self, params: Dict[str, Any], schedule: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Расчёт агрегатов по КП"""
        metrics = {}
        regular = schedule.get("regular", [])
        payments = [r["amount"] for r in regular if r["amount"] is not None]
        if payments:
            total = sum(payments)
            avg = total / len(payments)
            metrics["total_regular"] = total
            metrics["avg_payment"] = avg
            if params.get("price"):
                metrics["overpayment"] = total - params["price"]
        return metrics
