#!/bin/bash
# Инкрементальное обновление переписок по сделкам (комментарии + активности).
# Алерты (успех/ошибка) отправляет сам load_timeline.py через sync_alert.
set +e
LOG="$HOME/work/ts-b24/data/timeline.log"
SCRIPT_DIR="$HOME/work/ts-b24/scripts"

run_timestamp=$(date '+%Y-%m-%d %H:%M:%S')
echo "===== $run_timestamp =====" >> "$LOG"

/opt/homebrew/bin/python3 "$SCRIPT_DIR/load_timeline.py" --incremental 2>&1
rc=$?

echo "===== done rc=$rc =====" >> "$LOG"
exit $rc