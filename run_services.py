"""Run the web dashboard and Telegram bot as independently supervised services."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [service-supervisor] %(message)s",
)
logger = logging.getLogger("service-supervisor")
STOP = threading.Event()
CHECK_INTERVAL = 5
HEALTH_GRACE_SECONDS = 45
HEALTH_FAILURE_LIMIT = 8
HEALTH_URL = "http://127.0.0.1:5000/healthz"
SERVICES = {
    "dashboard": [
        sys.executable,
        "-m",
        "gunicorn",
        "--bind",
        "0.0.0.0:5000",
        "--workers",
        "1",
        "--threads",
        "4",
        "--timeout",
        "120",
        "app:app",
    ],
    "telegram-bot": [sys.executable, "-u", "telegram_bot.py"],
}


@dataclass
class Worker:
    name: str
    command: list[str]
    process: subprocess.Popen | None = None
    started_at: float = 0.0
    next_start_at: float = 0.0
    restart_delay: float = 2.0
    health_failures: int = 0


workers = {name: Worker(name=name, command=command) for name, command in SERVICES.items()}


def _handle_signal(signum, _frame):
    logger.info("Received signal %s; stopping child services", signum)
    STOP.set()


def _start(worker: Worker) -> None:
    if worker.name == "telegram-bot" and not os.environ.get("BOT_TOKEN").strip():
        logger.error("BOT_TOKEN is not configured; Telegram bot cannot start")
        worker.next_start_at = time.monotonic() + worker.restart_delay
        worker.restart_delay = min(worker.restart_delay * 2, 60)
        return
    try:
        worker.process = subprocess.Popen(worker.command, close_fds=True)
        worker.started_at = time.monotonic()
        worker.health_failures = 0
        logger.info("Started %s (pid=%s)", worker.name, worker.process.pid)
    except OSError:
        logger.exception("Could not start %s", worker.name)
        worker.process = None
        worker.next_start_at = time.monotonic() + worker.restart_delay
        worker.restart_delay = min(worker.restart_delay * 2, 60)


def _stop_worker(worker: Worker, reason: str) -> None:
    process = worker.process
    if process is None:
        return
    logger.warning("Stopping %s: %s", worker.name, reason)
    try:
        process.terminate()
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            logger.error("%s did not stop after SIGTERM; sending SIGKILL", worker.name)
            process.kill()
            process.wait(timeout=5)
    except OSError:
        logger.exception("Error stopping %s", worker.name)
    worker.process = None
    worker.next_start_at = time.monotonic() + worker.restart_delay
    worker.restart_delay = min(worker.restart_delay * 2, 60)


def _dashboard_healthy() -> bool:
    try:
        with urlopen(HEALTH_URL, timeout=3) as response:
            return response.status == 200
    except (OSError, URLError, TimeoutError):
        return False


def _monitor() -> None:
    while not STOP.wait(CHECK_INTERVAL):
        now = time.monotonic()
        for worker in workers.values():
            process = worker.process
            if process is not None:
                exit_code = process.poll()
                if exit_code is not None:
                    logger.error("%s exited with code %s", worker.name, exit_code)
                    worker.process = None
                    worker.next_start_at = now + worker.restart_delay
                    worker.restart_delay = min(worker.restart_delay * 2, 60)
                    continue
                if worker.name == "dashboard":
                    if now - worker.started_at < HEALTH_GRACE_SECONDS:
                        continue
                    if _dashboard_healthy():
                        worker.health_failures = 0
                        worker.restart_delay = 2.0
                    else:
                        worker.health_failures += 1
                        logger.warning(
                            "Dashboard health check failed (%s/%s)",
                            worker.health_failures,
                            HEALTH_FAILURE_LIMIT,
                        )
                        if worker.health_failures >= HEALTH_FAILURE_LIMIT:
                            _stop_worker(worker, "health endpoint remained unavailable")
                continue
            if now >= worker.next_start_at:
                logger.info("Restarting %s after service failure", worker.name)
                _start(worker)


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    logger.info("Starting independent dashboard and Telegram bot workers")
    for worker in workers.values():
        _start(worker)
    _monitor()
    logger.info("Stopping services gracefully")
    for worker in workers.values():
        if worker.process is not None:
            try:
                worker.process.terminate()
                worker.process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                worker.process.kill()
                worker.process.wait(timeout=5)
            except OSError:
                logger.exception("Error during shutdown of %s", worker.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
