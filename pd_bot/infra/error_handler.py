# -*- coding: utf-8 -*-
"""
infra/error_handler.py
Обёртка для функций с автоповторами, прогрессом и логированием.
"""

import functools
import time
from typing import Any, Callable, TypeVar, Optional

from infra.logger import get_logger

F = TypeVar("F", bound=Callable[..., Any])


class ErrorHandler:
    def __init__(self, retries: int = 3, base_delay: float = 1.0, backoff: float = 2.0):
        """
        :param retries: количество попыток
        :param base_delay: задержка перед первой повторной попыткой (сек)
        :param backoff: коэффициент роста задержки (экспоненциальный)
        """
        self.retries = retries
        self.base_delay = base_delay
        self.backoff = backoff
        self.logger = get_logger()

    def run(self, func: Callable[..., Any], *args, default: Optional[Any] = None, stage: str = "Неизвестный этап", **kwargs) -> Any:
        """
        Выполнить функцию с автоповторами и прогрессом.
        :param func: функция
        :param args: аргументы
        :param kwargs: именованные аргументы
        :param default: что вернуть при неудаче
        :param stage: название этапа (для логов)
        """
        delay = self.base_delay
        for attempt in range(1, self.retries + 1):
            try:
                self.logger.stage(stage).info(f"Попытка {attempt}/{self.retries}")
                result = func(*args, **kwargs)
                if attempt > 1:
                    self.logger.chat_status(f"{stage} — успешен с {attempt}-й попытки", status="ok")
                return result
            except Exception as e:
                percent = round((attempt / self.retries) * 100, 1)
                eta = f"{int(delay)} сек до след. попытки" if attempt < self.retries else "—"
                self.logger.error(f"Ошибка на этапе {stage} (попытка {attempt}/{self.retries}): {e}")
                self.logger.chat_status(f"{stage} — сбой {attempt}/{self.retries} ({percent}%, ETA {eta})", status="warn")
                if attempt < self.retries:
                    time.sleep(delay)
                    delay *= self.backoff
                else:
                    self.logger.error(f"{stage} — все {self.retries} попытки исчерпаны")
                    self.logger.chat_status(f"{stage} — провал после {self.retries} попыток", status="error")
                    return default


def safe_run(stage: str = "Неизвестный этап", retries: int = 3, base_delay: float = 1.0, backoff: float = 2.0, default: Optional[Any] = None):
    """
    Декоратор для функций с автоповторами.
    Пример:
        @safe_run(stage="Парсинг ОПУ", retries=3)
        def parse_opu(file): ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            handler = ErrorHandler(retries=retries, base_delay=base_delay, backoff=backoff)
            return handler.run(func, *args, default=default, stage=stage, **kwargs)
        return wrapper  # type: ignore
    return decorator


# Демонстрация
if __name__ == "__main__":
    log = get_logger()

    @safe_run(stage="Тестовая функция", retries=3, base_delay=1)
    def faulty(x):
        if x < 2:
            raise ValueError("Демо-ошибка")
        return f"Успех при x={x}"

    print(faulty(5))   # выполнится сразу
    print(faulty(1))   # провалится после 3 попыток
