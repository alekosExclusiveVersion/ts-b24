# Переписки по сделкам: комментарии ленты и активности (ts-b24)

Данные «переписок» по сделкам Битрикс24 выгружаются в локальную БД
`data/ts_b24.db` скриптом `scripts/load_timeline.py`.

## Источники (REST-вебхук)

- `crm.timeline.comment.list` — комментарии в ленте сделки (переписка с клиентом,
  внутренние заметки); фильтр `ENTITY_TYPE=deal`, `ENTITY_ID=<сделка>`.
- `crm.activity.list` — активности: встречи, звонки, письма, задачи, действия;
  фильтр `OWNER_TYPE_ID=2` (сделка) + `OWNER_ID=<сделка>`.

> `crm.timeline.list` (универсальная лента) вебхуку недоступен (22002),
> поэтому переписка тянется только через comment.list + activity.list.

## Таблицы БД

### `deal_comments`
| Колонка | Описание |
|---------|----------|
| `id` | ID комментария (PK) |
| `deal_id` | Сделка |
| `created` | Дата создания |
| `comment` | Текст комментария (BB-коды) |
| `author_id` | Автор (ID пользователя) |

### `deal_activities`
| Колонка | Описание |
|---------|----------|
| `id` | ID активности (PK) |
| `deal_id` | Сделка |
| `type_id` | Тип: 1 Встреча, 2 Звонок, 3 Задача, 4 Письмо, 5 Действие, 6 Пользовательское |
| `subject` | Тема |
| `description` | Описание/текст (у звонка — длительность, у письма — тело) |
| `description_type` | Тип описания (text/html) |
| `start_time`, `end_time` | Время |
| `completed` | Y/N |
| `direction` | 1 входящее, 2 исходящее |
| `provider_id`, `provider_type_id`, `provider_data` | Источник (email/telephony/...) |
| `author_id`, `responsible_id` | Кто создал / ответственный |
| `created`, `deadline`, `status` | Служебное |

Типы активностей: `crm.enum.activitytype` → 1 Встреча, 2 Звонок, 3 Задача,
4 Письмо, 5 Действие, 6 Пользовательское действие.

## Запуск

```bash
python3 scripts/load_timeline.py --since-days 365      # по DATE_CREATE за год
python3 scripts/load_timeline.py --by-modify           # отбор по DATE_MODIFY
python3 scripts/load_timeline.py --max-deals 500       # ограничить за запуск
python3 scripts/load_timeline.py --reset               # начать заново
```

- Обрабатываются только сделки, **созданные за последние N дней** (по умолч.
  365, ~24 тыс. сделок) из локальной таблицы `deals`.
- Работает через **batch-API** (`client.batch`): за один HTTP-запрос выполняется
  `2 × deals_per_batch` команд (по умолчанию 5 сделок за batch), чтобы щадить
  портал и не упираться в лимиты.
- Прогресс хранится в `kb_meta.timeline_deal_offset` — число обработанных
  сделок. Запуск со сбросом `--reset` очищает этот счётчик.
- Запись идемпотентна (`INSERT OR REPLACE`), повторный запуск не дублирует.

## Ограничения

- Текст комментария содержит BB-коды; для отображения чистить как в
  `web_search.clean_bb`.
- Поля файлов/записей звонков (аудио) в `crm.activity.list` вебхуку могут быть
  частично недоступны (как Диск b24) — на проверенной выборке берутся
  `SUBJECT`/`DESCRIPTION`/`PROVIDER_DATA`.
