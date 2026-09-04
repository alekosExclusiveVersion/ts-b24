#!/usr/bin/env python3
"""Детached-запуск load_timeline.py: двойной fork + setsid, чтобы процесс
переживал завершение родительской сессии (например, из CLI/агента с таймаутом).
"""
import os
import sys


def main():
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)
    cmd = [sys.executable, __file__.rsplit("/", 1)[0] + "/load_timeline.py"] + sys.argv[1:]
    log = __file__.rsplit("/", 1)[0] + "/../data/timeline.log"
    fd_out = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd_out, 1)
    os.dup2(fd_out, 2)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.execv(cmd[0], cmd)


if __name__ == "__main__":
    main()
