#!/bin/bash
# Обновление базы сделок b24: инкрементально (--update) по DATE_MODIFY.
# Алерты (успех/ошибка) отправляет сам build_kb_db.py через sync_alert.
# После успешного обновления FTS-индекс достраивается инкрементально
# (build_fts.py без --rebuild; --rebuild только вручную при рассинхроне).
set +e
LOG="$HOME/work/ts-b24/data/update.log"
SCRIPT_DIR="$HOME/work/ts-b24/scripts"

run_timestamp=$(date '+%Y-%m-%d %H:%M:%S')
echo "===== $run_timestamp =====" >> "$LOG"

/opt/homebrew/bin/python3 "$SCRIPT_DIR/build_kb_db.py" --update 2>&1
rc=$?

if [ $rc -eq 0 ]; then
  echo ">>> FTS incremental" >> "$LOG"
  /opt/homebrew/bin/python3 "$SCRIPT_DIR/build_fts.py" 2>&1
  rc=$?
fi

echo "===== done rc=$rc =====" >> "$LOG"
exit $rc