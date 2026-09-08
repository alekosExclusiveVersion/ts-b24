# Веб-интерфейс поиска по сделкам (ts-b24)

Интерактивный веб-поиск по локальной базе `data/ts_b24.db` (сделки, компании,
контакты, стадии, ответственные).

## Запуск

```bash
# алиас в ~/.zshrc
alias b24-search='/opt/homebrew/bin/python3 /Users/aleksei/work/ts-b24/scripts/web_search.py'

b24-search            # слушает 127.0.0.1:8000
```

Скрипт: `scripts/web_search.py` (HTTP-сервер без внешних зависимостей, только
stdlib + sqlite3). Шаблон страницы — `scripts/templates/index.html`.

Опции CLI: `--host`, `--port` (по умолч. 127.0.0.1:8000), `--db` (по умолч.
`data/ts_b24.db`).

## Публикация: https://b24.search/

Доступ наружу организован как у `kb.tradesoft.corp` — локальный nginx на этой
же машине выступает reverse proxy с self-signed-сертификатом.

| Компонент | Значение |
|-----------|----------|
| Внутренний адрес | `http://127.0.0.1:8000` |
| Внешний адрес | `https://b24.search/` |
| nginx server block | `/opt/homebrew/etc/nginx/servers/b24.search.conf` |
| Сертификат | `/opt/homebrew/etc/nginx/ssl/b24.search.{crt,key}` |
| Резолв | `/etc/hosts`: `127.0.0.1 b24.search` |
| IP машины | `192.168.128.56` (в SAN сертификата) |

Конфиг nginx: 443 SSL → `proxy_pass http://127.0.0.1:8000`, HTTP→HTTPS 301.
Сертификат self-signed (SAN: `DNS:b24.search`, `IP:192.168.128.56`, `IP:127.0.0.1`).

### Проверка

```bash
curl -sk https://b24.search/api/meta   # ожидается 200
```

> **Доступ из других машин (корп. сеть ts-work).** Mac на ts-work имеет
> статический IP `192.168.128.56/24`. `b24.search` — нестандартный домен
> (`.search`), corp-DNS его не обслуживает корректно. Для доступа с машин
> коллег нужно добавить hosts-запись `192.168.128.56 b24.search` (либо разнести
> готовый пакет `~/Work/colleagues-access.zip` — он прописывает hosts и импортирует
> сертификаты). Включённый Karing-VPN на Mac не мешает входящему доступу
> (входящие идут на интерфейс `en0`).

## Достижимость/тот же принцип, что у kb

- `kb.tradesoft.corp` → eval_server `127.0.0.1:8055` (`servers/kb.tradesoft.corp.conf`).
- `b24.search` → web_search `127.0.0.1:8000` (`servers/b24.search.conf`).
