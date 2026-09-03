# Поля сделок b24 (ts-b24)

Компактный справочник полей объекта «Сделка» Битрикс24, которые выгружаются
в таблицу `deals` локальной БД `data/ts_b24.db`.

## Базовые поля сделки (51 колонка)

| Поле | Описание |
|------|----------|
| `ID` | Идентификатор сделки |
| `TITLE` | Название сделки |
| `TYPE_ID` | Тип сделки (`deal_types`) |
| `STAGE_ID` | Стадия в воронке |
| `PREVIOUS_STAGE_ID` | Предыдущая стадия |
| `PROBABILITY` | Вероятность, % |
| `CURRENCY_ID` | Валюта (напр. RUB) |
| `OPPORTUNITY` | Сумма |
| `IS_MANUAL_OPPORTUNITY` | Сумма задана вручную |
| `TAX_VALUE` | Сумма налога |
| `LEAD_ID` | Связанный лид |
| `COMPANY_ID` | Связанная компания |
| `CONTACT_ID` | Связанный контакт |
| `MYCOMPANY_ID` | Моя компания |
| `QUOTE_ID` | Связанное коммерческое предложение |
| `BEGINDATE` | Дата начала |
| `CLOSEDATE` | Дата закрытия |
| `ASSIGNED_BY_ID` | Ответственный (ID) |
| `CREATED_BY_ID` | Кем создана (ID) |
| `MODIFY_BY_ID` | Кем изменена (ID) |
| `DATE_CREATE` | Дата создания |
| `DATE_MODIFY` | Дата изменения |
| `OPENED` | Доступность |
| `CLOSED` | Закрыта ли |
| `COMMENTS` | Комментарий |
| `ADDITIONAL_INFO` | Доп. информация |
| `LOCATION_ID` | Местоположение |
| `CATEGORY_ID` | Воронка (`deal_categories`) |
| `STAGE_SEMANTIC_ID` | Семантика стадии: P/S/F |
| `IS_NEW` | Новая |
| `IS_RECURRING` | Регулярная |
| `IS_RETURN_CUSTOMER` | Повторный клиент |
| `IS_REPEATED_APPROACH` | Повторное обращение |
| `SOURCE_ID` | Источник (`sources`) |
| `SOURCE_DESCRIPTION` | Описание источника |
| `ORIGINATOR_ID` | Внешний источник |
| `ORIGIN_ID` | Внешний ID |
| `MOVED_BY_ID` | Кто переместил (ID) |
| `MOVED_TIME` | Время перемещения |
| `LAST_ACTIVITY_TIME` | Время последней активности |
| `UTM_SOURCE/MEDIUM/CAMPAIGN/CONTENT/TERM` | UTM-метки |
| `PARENT_ID_141/166/177/1038` | Родительские сделки (быстрые/контекст) |
| `LAST_COMMUNICATION_TIME` | Время последнего общения |
| `LAST_ACTIVITY_BY` | Кто вёл последнюю активность (ID) |

## Справочники (таблицы)

- `deal_categories` — воронки (ID, NAME); на портале 19 воронок.
- `deal_stages` — стадии по воронкам (STATUS_ID, CATEGORY_ID, NAME, SEMANTIC_ID); 182 стадии.
- `sources` — источники сделок (ID, NAME); 116.
- `deal_types` — типы сделок (ID, NAME); 6.
- `users` — пользователи (ID, NAME, LAST_NAME, LOGIN).
  > Внимание: вебхук не имеет прав на `user.get`, поэтому таблица заполняется
  > только данными `profile` текущего пользователя (ID 176). Остальные
  > ответственные хранятся как ID в `deals.*_BY_ID`.
- `deal_files` — файлы/картинки сделок (задел):
  `id, deal_id, field_name, file_id, file_name, file_url, local_path, fetched_at, status`.
  > Сейчас Диск b24 и file-поля недоступны вебхуку, таблица пуста.

## Пользовательские поля-файлы (file-поля сделок)

Существуют 12 полей типа `file` (из `crm.item.fields`, entityTypeId=2):
`ufCrm_1750424044`, `ufCrm_1613540481`, `ufCrm_1611564211204`,
`ufCrm_1612697545967`, `ufCrm_1635849030184`, `ufCrm_634D12F9F11EF`,
`ufCrm_634D5C590B487`, `ufCrm_6384B973AD315`, `ufCrm_64369F742F892`,
`ufCrm_64369F744C2D1`, `ufCrm_1684444873362`, `ufCrmFilecEmployee`.

На проверенной выборке значения отсутствуют; доступ к Диску (`disk.*`) у
текущего вебхука закрыт (insufficient_scope).

## Полезные фильтры `crm.deal.list`

- по воронке: `filter={"CATEGORY_ID": "1"}`
- по статусу: `filter={"STAGE_SEMANTIC_ID": "P"}` (P открытые, S успешные, F неуспешные)
- по ответственному: `filter={"ASSIGNED_BY_ID": "176"}`
- по дате изменения: `filter={">DATE_MODIFY": "2026-01-01"}`
- по подстроке в названии: `filter={"%TITLE": "автосервис"}`
- по подстроке в комментарии: `filter={"%COMMENTS": "текст"}`
- комбинируемые (пересечение).
