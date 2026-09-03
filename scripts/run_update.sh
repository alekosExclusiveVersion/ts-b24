#!/bin/bash
# Обновление базы сделок b24: инкрементально (--update) по DATE_MODIFY
LOG="$HOME/work/ts-b24/data/update.log"
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  /opt/homebrew/bin/python3 "$HOME/work/ts-b24/scripts/build_kb_db.py" --update 2>&1
  echo "===== done rc=$? ====="
} >> "$LOG" 2>&1
