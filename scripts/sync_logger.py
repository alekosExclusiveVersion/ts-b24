import fcntl
import logging
import logging.handlers
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "data"

_loggers = {}
_locks = {}


def acquire_lock(name):
    """Неблокирующий файловый лок против двойного запуска cron-задач.

    Возвращает True, если лок захвачен. Повторный процесс должен
    тихо завершиться (вернётся False) — БД одна, параллельные
    писатели в неё не нужны.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"sync_{name}.lock"
    fh = open(path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    fh.write(str(os.getpid()))
    fh.flush()
    _locks[name] = fh
    return True


def get_logger(name, log_file=None):
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(f"ts_b24.{name}")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        path = LOG_DIR / (log_file or f"sync_{name}.log")
        path.parent.mkdir(parents=True, exist_ok=True)

        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    _loggers[name] = logger
    return logger
