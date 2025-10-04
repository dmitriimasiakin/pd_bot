# -*- coding: utf-8 -*-
"""
infra/logger.py
Расширенный логгер с прогрессом и ETA для PD-модели.
"""

import logging
import os
import threading
import time
from typing import Optional, Dict, Any, Callable
from logging.handlers import RotatingFileHandler
from datetime import datetime
import contextvars


# Контекст
_correlation_id_var = contextvars.ContextVar("correlation_id", default="-")
_stage_var = contextvars.ContextVar("stage", default="-")

# Синглтон
__LOGGER_SINGLETON = None
__LOGGER_LOCK = threading.Lock()

ChatCallback = Callable[[str, Dict[str, Any]], None]


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id_var.get()
        record.stage = _stage_var.get()
        return True


class ProgressTracker:
    """
    Трекер прогресса:
    - хранит общее число этапов/подэтапов
    - считает % выполнения
    - оценивает ETA
    """

    def __init__(self, total_steps: int):
        self.total_steps = total_steps
        self.completed_steps = 0
        self.start_time = time.time()

    def step_done(self):
        self.completed_steps += 1

    @property
    def percent(self) -> float:
        if self.total_steps == 0:
            return 100.0
        return round((self.completed_steps / self.total_steps) * 100, 1)

    @property
    def eta(self) -> str:
        if self.completed_steps == 0:
            return "—"
        elapsed = time.time() - self.start_time
        avg_per_step = elapsed / self.completed_steps
        remaining = (self.total_steps - self.completed_steps) * avg_per_step
        return f"{int(remaining)} сек"


class Logger:
    def __init__(
        self,
        log_dir: str = "logs",
        log_file: str = "pd_model.log",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ):
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, log_file)

        self._logger = logging.getLogger("PDModelLogger")
        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            ctx_filter = _ContextFilter()

            file_handler = RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | corr=%(correlation_id)s | stage=%(stage)s | %(message)s"))
            file_handler.addFilter(ctx_filter)
            self._logger.addHandler(file_handler)

            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
            console_handler.addFilter(ctx_filter)
            self._logger.addHandler(console_handler)

            self._logger.propagate = False

        self._chat_callback: Optional[ChatCallback] = None
        self.progress: Optional[ProgressTracker] = None

    # ========== Базовое логирование ==========
    def info(self, msg: str): self._logger.info(msg)
    def warning(self, msg: str): self._logger.warning(msg)
    def error(self, msg: str): self._logger.error(msg)
    def exception(self, msg: str): self._logger.exception(msg)

    def set_chat_callback(self, callback: ChatCallback):
        self._chat_callback = callback

    def set_correlation_id(self, correlation_id: str):
        _correlation_id_var.set(correlation_id or "-")

    def stage(self, stage_name: str):
        _stage_var.set(stage_name)
        return self

    # ========== Прогресс и ETA ==========
    def init_progress(self, total_steps: int):
        """Инициализировать прогресс"""
        self.progress = ProgressTracker(total_steps)
        self.info(f"Прогресс: 0/{total_steps} (0%)")

    def step_done(self, step_name: str):
        """Завершение подэтапа"""
        if not self.progress:
            return
        self.progress.step_done()
        percent = self.progress.percent
        eta = self.progress.eta
        bar = self._progress_bar(percent)
        msg = f"{bar} {percent}% | ETA: {eta} | Завершён: {step_name}"
        self.info(msg)
        self.chat_status(f"{step_name} ({percent}%, ETA {eta})", status="ok")

    def _progress_bar(self, percent: float, length: int = 20) -> str:
        filled = int(length * percent // 100)
        return "[" + "█" * filled + "-" * (length - filled) + "]"

    # ========== Статусы для чата ==========
    def chat_status(self, stage: str, status: str = "ok", extra: Optional[Dict[str, Any]] = None) -> str:
        emoji = {"ok": "✅", "warn": "⚠", "error": "🟥"}.get(status, "ℹ️")
        message = f"{emoji} {stage}"
        self.info(f"[CHAT] {message}")
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": status,
            "stage": _stage_var.get(),
            "correlation_id": _correlation_id_var.get(),
            "percent": self.progress.percent if self.progress else None,
            "eta": self.progress.eta if self.progress else None,
        }
        if extra:
            payload.update(extra)
        if self._chat_callback:
            try:
                self._chat_callback(message, payload)
            except Exception as e:
                self.warning(f"Ошибка chat callback: {e}")
        return message


def get_logger() -> Logger:
    global __LOGGER_SINGLETON
    if __LOGGER_SINGLETON is None:
        with __LOGGER_LOCK:
            if __LOGGER_SINGLETON is None:
                __LOGGER_SINGLETON = Logger()
    return __LOGGER_SINGLETON


# Демонстрация
if __name__ == "__main__":
    log = get_logger()
    log.set_correlation_id("demo-001")
    log.init_progress(total_steps=5)

    for i in range(5):
        time.sleep(0.5)
        log.step_done(f"Этап {i+1}")
