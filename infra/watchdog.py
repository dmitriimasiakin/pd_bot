# -*- coding: utf-8 -*-
"""
infra/watchdog.py
Боевой watchdog для PD-модели.
"""

import threading
import time
from typing import Callable, Dict, Any, Optional

from infra.logger import get_logger
from infra.error_handler import ErrorHandler


class Watchdog:
    """
    Watchdog:
    - следит за задачами по heartbeat и таймауту
    - показывает прогресс (% и ETA)
    - перезапускает зависшие задачи
    """

    def __init__(self, check_interval: float = 5.0, timeout: float = 60.0):
        """
        :param check_interval: интервал проверки задач (сек)
        :param timeout: время без heartbeat или выполнения (сек)
        """
        self.check_interval = check_interval
        self.timeout = timeout
        self.logger = get_logger()

        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def register_task(self, name: str, func: Callable, *args, total_steps: Optional[int] = None, **kwargs):
        """
        Зарегистрировать задачу для мониторинга
        :param name: имя задачи
        :param func: функция
        :param total_steps: если задача многошаговая, указываем количество шагов
        """
        with self._lock:
            self._tasks[name] = {
                "func": func,
                "args": args,
                "kwargs": kwargs,
                "last_heartbeat": time.time(),
                "last_start": None,
                "progress_total": total_steps,
                "progress_done": 0,
                "thread": None,
            }
        self.logger.info(f"Задача {name} зарегистрирована в watchdog")
        self._start_task(name)

    def heartbeat(self, name: str, step_done: bool = False):
        """Обновить heartbeat, при необходимости — отметить завершение шага"""
        with self._lock:
            if name in self._tasks:
                self._tasks[name]["last_heartbeat"] = time.time()
                if step_done:
                    self._tasks[name]["progress_done"] += 1

    def stop(self):
        """Остановить watchdog"""
        self._stop_event.set()
        self._thread.join()

    # ======= Внутренние =======

    def _start_task(self, name: str):
        """Запустить задачу в отдельном потоке"""
        task = self._tasks[name]

        def runner():
            handler = ErrorHandler()
            while not self._stop_event.is_set():
                task["last_start"] = time.time()
                result = handler.run(
                    task["func"],
                    *task["args"],
                    stage=f"Watchdog:{name}",
                    default=None,
                    **task["kwargs"],
                )
                self.logger.info(f"Задача {name} завершена. Перезапуск через 1 сек.")
                time.sleep(1)

        t = threading.Thread(target=runner, daemon=True)
        task["thread"] = t
        t.start()
        self.logger.chat_status(f"Задача {name} запущена", status="ok")

    def _loop(self):
        """Основной цикл мониторинга"""
        while not self._stop_event.is_set():
            now = time.time()
            with self._lock:
                for name, task in list(self._tasks.items()):
                    last_hb = task["last_heartbeat"]
                    last_start = task["last_start"]

                    # Вычисление прогресса
                    percent, eta = self._calc_progress(task)

                    # Проверка heartbeat
                    if now - last_hb > self.timeout:
                        self.logger.warning(f"Задача {name} зависла по heartbeat (> {self.timeout} сек)")
                        self.logger.chat_status(f"{name} — зависание (heartbeat), {percent}% ETA {eta}", status="warn")
                        self._restart_task(name)
                        continue

                    # Проверка таймаута выполнения
                    if last_start and (now - last_start > self.timeout):
                        self.logger.error(f"Задача {name} превысила таймаут выполнения ({self.timeout} сек)")
                        self.logger.chat_status(f"{name} — таймаут, {percent}% ETA {eta}", status="error")
                        self._restart_task(name)
            time.sleep(self.check_interval)

    def _restart_task(self, name: str):
        """Перезапустить задачу"""
        self.logger.error(f"Перезапуск задачи {name}")
        try:
            t = self._tasks[name].get("thread")
            if t and t.is_alive():
                self.logger.warning(f"Старый поток {name} ещё работает, создаётся новый")
            self._start_task(name)
        except Exception as e:
            self.logger.exception(f"Ошибка при перезапуске {name}: {e}")

    def _calc_progress(self, task: Dict[str, Any]):
        """Расчёт % и ETA"""
        total = task.get("progress_total")
        done = task.get("progress_done", 0)
        if total and total > 0:
            percent = round((done / total) * 100, 1)
            elapsed = time.time() - (task.get("last_start") or time.time())
            avg = elapsed / done if done > 0 else 0
            remaining = (total - done) * avg if avg > 0 else 0
            eta = f"{int(remaining)} сек"
            return percent, eta
        return 0.0, "—"
