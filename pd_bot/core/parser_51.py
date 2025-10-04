# -*- coding: utf-8 -*-
"""
core/parser_51.py
Парсер карточки счёта 51 (расчётный счёт) с приоритетом Excel-таблиц.

Возможности:
- Умное определение строк заголовка и сопоставление колонок (date/debit/credit/balance/counterparty/description)
- Разбор всех строк операций (Дт/Кт), конвертация чисел (пробелы, запятая, отрицательные в скобках)
- Построение остатков по дням, неделям, месяцам (если нет явного 'Остаток' — считаем кумулятивно)
- Анализ контрагентов (ТОП-5 по поступлениям и списаниям, доли)
- Стресс-тест: вычитание ежемесячного платежа из месячного окончания, флаг возможной просрочки/дефолта
"""

from __future__ import annotations

import re
import math
import datetime as dt
from typing import Dict, Any, Union, List, Optional, Tuple
from collections import defaultdict, Counter

import pandas as pd

from infra.logger import get_logger
from infra.error_handler import safe_run


NUM_RE = re.compile(r"\(?-?\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d+)?\)?")  # поддержка (1 234,56) и пробелов
DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")


def _num_to_float(s: Any) -> Optional[float]:
    """Приведение строкового денежного значения к float: '1 234,56' -> 1234.56 ; '(1 000)' -> -1000.0"""
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return None
    m = NUM_RE.search(s.replace("\u00A0", " "))
    if not m:
        return None
    val = m.group(0)
    neg = val.startswith("(") and val.endswith(")")
    val = val.replace("(", "").replace(")", "").replace(" ", "").replace("\u00A0", "")
    val = val.replace(",", ".")
    try:
        x = float(val)
        return -x if neg else x
    except Exception:
        return None


def _parse_date(s: Any) -> Optional[dt.date]:
    """Парсинг даты в формате DD.MM.YYYY из ячейки."""
    if s is None:
        return None
    if isinstance(s, (dt.date, dt.datetime, pd.Timestamp)):
        return (pd.to_datetime(s)).date()
    s = str(s)
    m = DATE_RE.search(s)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(0), "%d.%m.%Y").date()
    except Exception:
        return None


class Card51Parser:
    def __init__(self):
        self.logger = get_logger()

    @safe_run(stage="Парсинг 51 счета", retries=2, base_delay=1.0, backoff=2.0, default={})
    def parse(self, raw_data: Union[pd.DataFrame, str], monthly_payment: float = 0.0) -> Dict[str, Any]:
        """
        Основной вход: разбор карточки 51.
        :param raw_data: DataFrame (предпочтительно Excel) или плоский текст
        :param monthly_payment: ежемесячный платёж для стресс-теста (руб.)
        :return: структура с транзакциями, потоками, остатками, контрагентами и стресс-тестом
        """
        df = self._to_dataframe(raw_data)
        df_norm, colmap = self._normalize_and_map_columns(df)

        txns = self._extract_transactions(df_norm, colmap)
        cashflow = self._analyze_cashflow(txns)
        balances = self._analyze_balances(txns, colmap, monthly_payment)
        counterparties = self._analyze_counterparties(txns, cashflow)

        return {
            "columns": colmap,
            "transactions": txns,
            "cashflow": cashflow,
            "balances": balances,
            "counterparties": counterparties,
        }

    # -------------------------- Подготовка данных --------------------------

    def _to_dataframe(self, raw: Union[pd.DataFrame, str]) -> pd.DataFrame:
        """Любые входные данные -> DataFrame. PDF/текст разбираем построчно."""
        if isinstance(raw, pd.DataFrame):
            df = raw.copy()
        else:
            lines = [l.strip() for l in str(raw).splitlines() if l.strip()]
            df = pd.DataFrame(lines, columns=["raw"])
        return df

    def _normalize_and_map_columns(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
        """
        Поиск строки заголовка и сопоставление колонок.
        Возвращает нормализованный DF с именованными колонками + карту {role: column_name_or_None}.
        Возможные роли: date, debit, credit, balance, counterparty, description
        """
        # Если колонок одна — вероятно, это текстовая выгрузка
        if df.shape[1] == 1:
            # попробуем выдрать через regex построчно позже
            return df.rename(columns={df.columns[0]: "raw"}), {"date": None, "debit": None, "credit": None, "balance": None, "counterparty": None, "description": "raw"}

        # Попробуем найти строку заголовка в первых 10 строках
        header_row_idx = None
        # приведём всё к строке для эвристик
        df_preview = df.head(10).fillna("").astype(str)
        for i in range(min(10, len(df_preview))):
            row_text = " ".join(df_preview.iloc[i].tolist()).lower()
            hits = sum(k in row_text for k in ["дата", "контраг", "дебет", "кредит", "остат", "назнач", "опис"])
            if hits >= 2:
                header_row_idx = i
                break

        if header_row_idx is not None:
            headers = df.iloc[header_row_idx].fillna("").astype(str).str.strip().str.lower().tolist()
            df2 = df.iloc[header_row_idx + 1:].copy()
            df2.columns = self._make_unique_headers(headers, df2.shape[1])
        else:
            # считаем, что первая строка уже заголовки (или Excel с именами)
            headers = df.iloc[0].fillna("").astype(str).str.strip().str.lower().tolist()
            df2 = df.iloc[1:].copy()
            df2.columns = self._make_unique_headers(headers, df2.shape[1])

        # Сопоставление ролей колонок
        colmap = self._infer_roles(df2.columns.tolist())

        # Дополнительная эвристика: если не нашли date/debit/credit, попробуем по содержимому
        sample = df2.head(200).fillna("").astype(str)
        if colmap["date"] is None:
            colmap["date"] = self._guess_date_col(sample)
        if colmap["debit"] is None or colmap["credit"] is None:
            dcol, ccol = self._guess_amount_cols(sample, prefer=("дебет", "кредит"))
            colmap["debit"] = colmap["debit"] or dcol
            colmap["credit"] = colmap["credit"] or ccol
        if colmap["balance"] is None:
            colmap["balance"] = self._guess_balance_col(sample)
        if colmap["counterparty"] is None:
            colmap["counterparty"] = self._guess_counterparty_col(sample)
        if colmap["description"] is None:
            colmap["description"] = self._guess_description_col(sample, exclude=[colmap.get("counterparty")])

        return df2.reset_index(drop=True), colmap

    @staticmethod
    def _make_unique_headers(headers: List[str], n: int) -> List[str]:
        """Гарантирует уникальность имён колонок."""
        res, seen = [], {}
        for i in range(n):
            base = headers[i] if i < len(headers) else f"col_{i}"
            name = base or f"col_{i}"
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            res.append(name)
        return res

    @staticmethod
    def _infer_roles(cols: List[str]) -> Dict[str, Optional[str]]:
        """Грубое сопоставление ролей по заголовкам."""
        low = [c.lower() for c in cols]
        def find(one_of: List[str]) -> Optional[str]:
            for kw in one_of:
                for c in low:
                    if kw in c:
                        return cols[low.index(c)]
            return None

        return {
            "date": find(["дата"]),
            "debit": find(["дебет", "дт"]),
            "credit": find(["кредит", "кт"]),
            "balance": find(["остат", "сальдо"]),
            "counterparty": find(["контраг", "платель", "получат", "банк", "клиент"]),
            "description": find(["назнач", "опис", "коммент", "основан"]),
        }

    @staticmethod
    def _guess_date_col(sample: pd.DataFrame) -> Optional[str]:
        best, best_hits = None, -1
        for c in sample.columns:
            hits = sum(sample[c].astype(str).str.contains(DATE_RE).fillna(False))
            if hits > best_hits:
                best, best_hits = c, hits
        return best if best_hits > 0 else None

    @staticmethod
    def _guess_amount_cols(sample: pd.DataFrame, prefer=("дебет", "кредит")) -> Tuple[Optional[str], Optional[str]]:
        cand = []
        for c in sample.columns:
            # считаем количество ячеек, которые выглядят как деньги
            vals = sample[c].astype(str).apply(lambda x: NUM_RE.search(x.replace("\u00A0", " ")) is not None)
            score = vals.sum()
            if score > 0:
                cand.append((c, score))
        cand.sort(key=lambda x: x[1], reverse=True)
        # попытаемся выбрать 2 столбца с максимумом
        cands = [c for c, _ in cand[:3]]
        # предпочтём по имени
        dcol = next((c for c in cands if any(p in c.lower() for p in [prefer[0], "дт"])), None)
        ccol = next((c for c in cands if any(p in c.lower() for p in [prefer[1], "кт"] and c != dcol)), None)
        # если не нашли по имени — берём топ-2
        if dcol is None and len(cands) >= 1:
            dcol = cands[0]
        if ccol is None and len(cands) >= 2:
            ccol = cands[1] if cands[1] != dcol else (cands[2] if len(cands) > 2 else None)
        return dcol, ccol

    @staticmethod
    def _guess_balance_col(sample: pd.DataFrame) -> Optional[str]:
        for c in sample.columns:
            if any(k in c.lower() for k in ["остат", "сальдо"]):
                return c
        # как эвристика — столбец с большим количеством денег и без явных 'дт/кт'
        cand = []
        for c in sample.columns:
            if any(k in c.lower() for k in ["дт", "кт", "дебет", "кредит"]):
                continue
            vals = sample[c].astype(str).apply(lambda x: NUM_RE.search(x.replace("\u00A0", " ")) is not None)
            sc = vals.sum()
            if sc > 0:
                cand.append((c, sc))
        cand.sort(key=lambda x: x[1], reverse=True)
        return cand[0][0] if cand else None

    @staticmethod
    def _guess_counterparty_col(sample: pd.DataFrame) -> Optional[str]:
        for c in sample.columns:
            if any(k in c.lower() for k in ["контраг", "платель", "получат", "клиент", "банк", "инн"]):
                return c
        # fallback: описание
        return None

    @staticmethod
    def _guess_description_col(sample: pd.DataFrame, exclude: List[Optional[str]] = None) -> Optional[str]:
        exclude = set(x for x in exclude or [] if x)
        for c in sample.columns:
            if c in exclude:
                continue
            if any(k in c.lower() for k in ["назнач", "опис", "основан", "назначение платежа"]):
                return c
        return None

    # -------------------------- Извлечение транзакций --------------------------

    def _extract_transactions(self, df: pd.DataFrame, colmap: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
        txns: List[Dict[str, Any]] = []

        # Если только текстовая колонка — парсим regex'ами
        if df.shape[1] == 1 and "raw" in df.columns:
            for _, row in df.iterrows():
                line = str(row["raw"])
                txns.append({
                    "date": _parse_date(line),
                    "debit": _num_to_float(line) if "деб" in line.lower() else None,
                    "credit": _num_to_float(line) if "кред" in line.lower() else None,
                    "balance": None,
                    "counterparty": self._extract_counterparty_free(line),
                    "description": line[:500],
                })
            return [t for t in txns if any([t["date"], t["debit"], t["credit"], t["counterparty"]])]

        # Иначе — нормальная таблица
        def col(name: str) -> Optional[pd.Series]:
            c = colmap.get(name)
            return df[c] if c in df.columns else None

        s_date = col("date")
        s_deb = col("debit")
        s_cred = col("credit")
        s_bal = col("balance")
        s_cp = col("counterparty")
        s_desc = col("description")

        for i in range(len(df)):
            date = _parse_date(s_date.iloc[i]) if s_date is not None else _parse_date(" ".join(map(str, df.iloc[i].tolist())))
            debit = _num_to_float(s_deb.iloc[i]) if s_deb is not None else None
            credit = _num_to_float(s_cred.iloc[i]) if s_cred is not None else None
            balance = _num_to_float(s_bal.iloc[i]) if s_bal is not None else None
            counterparty = None
            if s_cp is not None:
                counterparty = self._normalize_counterparty(str(s_cp.iloc[i]))
            if not counterparty and s_desc is not None:
                counterparty = self._extract_counterparty_free(str(s_desc.iloc[i]))
            description = str(s_desc.iloc[i])[:500] if s_desc is not None else None

            # пропустим пустые строки
            if not any([date, debit, credit, balance, counterparty, description]):
                continue

            txns.append({
                "date": date,
                "debit": debit,
                "credit": credit,
                "balance": balance,
                "counterparty": counterparty,
                "description": description,
            })

        # отсортируем по дате (неизвестные — в начало)
        txns.sort(key=lambda x: x["date"] or dt.date.min)
        return txns

    @staticmethod
    def _normalize_counterparty(s: str) -> Optional[str]:
        s = (s or "").strip()
        if not s:
            return None
        s_l = s.lower()
        # нормализация частых форм
        s_l = s_l.replace("ооо ", "ООО ").replace("зао ", "ЗАО ").replace("ип ", "ИП ").replace("ао ", "АО ")
        # восстановим исходный регистр для ключевых аббревиатур
        return s.strip()

    @staticmethod
    def _extract_counterparty_free(text: str) -> Optional[str]:
        t = text or ""
        # ИНН
        m = re.search(r"\b\d{10}\b|\b\d{12}\b", t)
        if m:
            return f"ИНН {m.group(0)}"
        # юрлица/ИП
        m2 = re.search(r"(ООО|ЗАО|АО|ИП)\s+[A-Za-zА-Яа-я0-9\"'«»\-\s]{2,}", t, flags=re.IGNORECASE)
        if m2:
            return m2.group(0).strip()
        return None

    # -------------------------- Аналитика потоков и остатков --------------------------

    def _analyze_cashflow(self, txns: List[Dict[str, Any]]) -> Dict[str, Any]:
        cash_in = sum((t.get("debit") or 0) for t in txns)
        cash_out = sum((t.get("credit") or 0) for t in txns)
        delta = cash_in - cash_out

        # помесячно
        by_month_in = defaultdict(float)
        by_month_out = defaultdict(float)
        for t in txns:
            if not t.get("date"):
                continue
            m = t["date"].strftime("%Y-%m")
            if t.get("debit"):
                by_month_in[m] += t["debit"]
            if t.get("credit"):
                by_month_out[m] += t["credit"]

        return {
            "cash_in": cash_in,
            "cash_out": cash_out,
            "delta": delta,
            "by_month_in": dict(by_month_in),
            "by_month_out": dict(by_month_out),
        }

    def _analyze_balances(self, txns: List[Dict[str, Any]], colmap: Dict[str, Optional[str]], monthly_payment: float) -> Dict[str, Any]:
        # если есть колонка 'balance' — используем её; иначе считаем сами от 0 или от входящего сальдо если найдём
        opening = None
        for t in txns[:5]:
            if t.get("description") and any(k in str(t["description"]).lower() for k in ["входящий", "начальн"]):
                # попробуем считать это входящим сальдо
                bal = t.get("balance")
                if bal is None:
                    # иногда входящий указан в Дт/Кт
                    bal = (t.get("debit") or 0) - (t.get("credit") or 0)
                opening = bal if isinstance(bal, (int, float)) else 0.0
                break
        if opening is None:
            opening = 0.0

        daily = defaultdict(float)
        curr = opening
        for t in txns:
            if t.get("balance") is not None:
                curr = t["balance"]  # доверяем выгрузке банка/БУ
            else:
                if t.get("debit"):
                    curr += t["debit"]
                if t.get("credit"):
                    curr -= t["credit"]
            d = t.get("date") or dt.date.min
            daily[d] = curr

        # сводки
        by_month_last, by_week_last = defaultdict(lambda: None), defaultdict(lambda: None)
        for d in sorted(daily):
            m = d.strftime("%Y-%m") if d != dt.date.min else "unknown"
            w = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]}" if d != dt.date.min else "unknown"
            by_month_last[m] = daily[d]
            by_week_last[w] = daily[d]

        summary = {
            "daily_min": min(daily.values()) if daily else None,
            "daily_max": max(daily.values()) if daily else None,
            "daily_avg": (sum(daily.values()) / len(daily)) if daily else None,
            "by_month_end": dict(by_month_last),
            "by_week_end": dict(by_week_last),
        }

        # стресс-тест: вычитаем ежемесячный платёж из конца месяца
        stress = {}
        if monthly_payment and monthly_payment > 0:
            for m, end_bal in summary["by_month_end"].items():
                if end_bal is None:
                    continue
                after = end_bal - monthly_payment
                stress[m] = {
                    "end_balance_after_payment": after,
                    "shortfall": -after if after < 0 else 0.0,
                    "default_risk": after < 0,
                }

        return {"summary": summary, "stress_test": stress}

    # -------------------------- Контрагенты и концентрация --------------------------

    def _analyze_counterparties(self, txns: List[Dict[str, Any]], cashflow: Dict[str, Any]) -> Dict[str, Any]:
        inflow, outflow = Counter(), Counter()
        total_in, total_out = cashflow["cash_in"], cashflow["cash_out"]

        for t in txns:
            cp = t.get("counterparty")
            if not cp:
                continue
            if t.get("debit"):
                inflow[cp] += t["debit"]
            if t.get("credit"):
                outflow[cp] += t["credit"]

        def top_with_share(counter: Counter, total: float, k: int = 5):
            top = counter.most_common(k)
            res = []
            for name, amt in top:
                share = (amt / total) if total else 0.0
                res.append({"name": name, "amount": amt, "share": share})
            # концентрация
            top1 = res[0]["share"] if res else 0.0
            top3 = sum(x["share"] for x in res[:3])
            top5 = sum(x["share"] for x in res[:5])
            return {"top": res, "concentration": {"top1": top1, "top3": top3, "top5": top5}}

        return {
            "inflow": top_with_share(inflow, total_in, 5),
            "outflow": top_with_share(outflow, total_out, 5),
        }
