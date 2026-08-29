<div align="center">

# Ozon → Google Sheets

**Выгрузка финансовых начислений Ozon в Google Sheets**

**Русский** · [English](https://github.com/sotchenkov/ozon_to_google_sheets/blob/main/README.en.md)

[![CI](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml/badge.svg)](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml)
[![Coverage ≥95%](https://img.shields.io/badge/coverage-%E2%89%A595%25-brightgreen?style=flat-square)](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml)
[![Python 3.10–3.14](https://img.shields.io/badge/Python-3.10%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: Elastic 2.0](https://img.shields.io/badge/license-Elastic%202.0-005571?style=flat-square)](LICENSE)

[Запуск](#быстрый-запуск) · [Доступы](#настройка-доступов) ·
[Таблица](#пример-таблицы) · [Поддержка](#помощь-и-поддержка)

</div>

Приложение забирает финансовые начисления из Ozon Seller API и записывает их в Google Sheets.

## Быстрый запуск

Понадобятся Docker с Compose v2, ключ Ozon Seller API, Google-таблица и JSON-ключ сервисного
аккаунта Google.

### 1. Подготовьте файлы

```console
git clone https://github.com/sotchenkov/ozon_to_google_sheets.git
cd ozon_to_google_sheets
cp .env.example .env
mkdir -p secrets logs
cp /path/to/service-account.json secrets/google-service-account.json
chmod 600 .env
chmod 700 secrets
chmod 600 secrets/google-service-account.json
```

Как получить ключи и открыть доступ к таблице, описано в разделе
[Настройка доступов](#настройка-доступов).

### 2. Заполните `.env`

```dotenv
OZON_TOKEN=replace-with-ozon-api-token
OZON_CLIENT_ID=replace-with-ozon-client-id
GOOGLE_CREDENTIALS_PATH=secrets/google-service-account.json
GOOGLE_SPREADSHEET_ID=replace-with-google-spreadsheet-id
GOOGLE_WORKSHEET_ID=0

# Необязательный период в формате YYYY-MM-DD
# OZON_DATE_FROM=2026-01-01
# OZON_DATE_TO=2026-01-31
```

Значения в примере вымышлены.

### 3. Запустите

На Linux-сервере сначала выдайте контейнеру права на [`secrets/` и `logs/`](#права-на-сервере).

```console
docker compose up --pull always --abort-on-container-exit --exit-code-from app
docker compose down
```

Контейнер загрузит начисления в выбранный лист и завершится. Заголовки займут строку `A1:U1`,
данные появятся ниже. Предупреждения и ошибки записываются в `logs/logs.log`.

### Запуск без Docker

Установите [uv](https://docs.astral.sh/uv/getting-started/installation/), затем выполните:

```console
uv sync --locked --no-dev
uv run --no-sync ozon-to-google-sheets
```

## Настройка доступов

### Ozon API

1. Откройте [Ozon Seller](https://seller.ozon.ru/) и перейдите в настройки Seller API.
2. Скопируйте **Client ID** — это `OZON_CLIENT_ID`.
3. Создайте API-ключ с доступом к финансовым данным — это `OZON_TOKEN`.
4. Если доступны разные роли, выберите минимальную роль только для чтения.

Названия пунктов в кабинете могут меняться. Актуальный раздел:
[документация Ozon Seller API](https://docs.ozon.ru/api/seller/).

### Google service account

1. Создайте или выберите проект в [Google Cloud Console](https://console.cloud.google.com/).
2. Включите **Google Sheets API**.
3. Откройте **IAM & Admin → Service Accounts** и создайте сервисный аккаунт.
4. В карточке аккаунта выберите **Keys → Add key → Create new key → JSON**.
5. Сохраните скачанный файл как `secrets/google-service-account.json`.
6. Откройте целевую Google-таблицу, нажмите **Поделиться** и добавьте адрес из поля
   `client_email` этого JSON-файла с ролью **Редактор**.

Таблицу не нужно делать публичной. Проектная IAM-роль сервисному аккаунту тоже не нужна.

Официальные инструкции Google:
[создание credentials](https://developers.google.com/workspace/guides/create-credentials) и
[управление JSON-ключами](https://cloud.google.com/iam/docs/keys-create-delete).

### ID таблицы и листа

Откройте целевую таблицу в браузере. Для такого адреса:

```text
https://docs.google.com/spreadsheets/d/1AbCdEfGhExample/edit#gid=123456789
```

- `GOOGLE_SPREADSHEET_ID=1AbCdEfGhExample` — значение между `/d/` и `/edit`;
- `GOOGLE_WORKSHEET_ID=123456789` — число после `gid=`.

Приложение не создаёт таблицу или лист: их нужно подготовить заранее.

## Настройки

| Переменная | Назначение |
| --- | --- |
| `OZON_TOKEN` | API-ключ Ozon Seller |
| `OZON_CLIENT_ID` | Client ID продавца |
| `GOOGLE_SPREADSHEET_ID` | ID Google-таблицы |
| `GOOGLE_WORKSHEET_ID` | Числовой `gid` листа |
| `GOOGLE_CREDENTIALS_PATH` | Путь к JSON-ключу Google; рекомендуемый вариант |
| `GOOGLE_CREDENTIALS_JSON` | JSON-ключ целиком из внешнего хранилища секретов |
| `OZON_DATE_FROM` | Начало периода, `YYYY-MM-DD` |
| `OZON_DATE_TO` | Конец периода, `YYYY-MM-DD` |
| `OZON_ENV_FILE` | Другой env-файл для Docker Compose вместо `.env` |

Укажите только один источник Google credentials: `GOOGLE_CREDENTIALS_PATH` или
`GOOGLE_CREDENTIALS_JSON`. Переменные окружения процесса имеют приоритет над `.env`.

### Период выгрузки

Обе даты входят в период. Часовой пояс — `Europe/Moscow`.

| `OZON_DATE_FROM` | `OZON_DATE_TO` | Что загрузится |
| --- | --- | --- |
| не указана | не указана | Вчера и сегодня |
| указана | не указана | С указанной даты по сегодня |
| не указана | указана | Только указанная дата |
| указана | указана | Весь указанный период |

Допустимы даты от `2022-01-01` до сегодняшнего дня. Начало не может быть позже окончания.

### Коды завершения

| Код | Значение |
| ---: | --- |
| `0` | Выгрузка завершилась успешно, в том числе если за период нет начислений |
| `1` | Ошибка Ozon, Google Sheets, сети, сверки данных или уже запущена другая синхронизация |
| `2` | Ошибка в настройках или приложению переданы аргументы командной строки |

Код контейнера совпадает с кодом приложения. Команда из быстрого запуска возвращает его благодаря
`--exit-code-from app`.

## Пример таблицы

| ID операции | Дата начисления | Тип начисления | Номер отправления или идентификатор услуги | SKU | Количество | Выручка | Ставка комиссии | Комиссия Ozon | Логистика | Последняя миля | Обратная логистика | Возвраты и отмены | Реклама | Эквайринг | Хранение | Упаковка | Прочие | Компенсации | Неопознанные начисления | Итого |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 910001 | 2026-01-15 | POSTING | posting-demo-0001 | 900000001 | 2 | 100,00 | 10% | -10,00 | -7,00 | -5,00 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 123,00 |
| 910001 | 2026-01-15 | POSTING | posting-demo-0001 | 900000002 | 1 | 50,00 | 10% | -5,00 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |  |

Одна операция Ozon может включать несколько SKU, поэтому её ID повторяется в нескольких строках.
Ozon передаёт «Итого» для всей операции, а не отдельно для каждого SKU: приложение записывает эту
сумму в первую строку операции и оставляет её пустой в остальных. Так обычная сумма по столбцу не
умножает итог операции на количество SKU.

### Категории, неизвестные начисления и сверка

Известные начисления распределяются по отдельным бизнес-категориям: логистика, последняя миля,
обратная логистика, возвраты и отмены, реклама, эквайринг, хранение, упаковка, прочие и
компенсации. Только неизвестные приложению типы попадают в «Неопознанные начисления». В таком
случае предупреждение в логе содержит исходные `type_id` и `type_name`. Если Ozon не передал
денежную детализацию операции, сверка не пройдёт и данные не будут записаны.

Перед записью приложение сверяет сумму всех денежных полей операции с «Итого» от Ozon. При
расхождении текущая дата не записывается, а запуск завершается с кодом `1`. Проверьте предупреждения
и ошибки в `logs/logs.log`, затем сравните итог за период с финансовым отчётом в кабинете Ozon.

## Повторные запуски

Проект можно запускать повторно: уже загруженные операции обновятся, новые
добавятся, а операции за другие даты останутся на месте. Ручные изменения в листе
выгрузки внутри диапазона `A:U` могут быть перезаписаны.

Если лист пустой, заголовки добавятся автоматически — даже когда Ozon не вернул ни одного
начисления. Такой запуск считается успешным. Если в первой строке уже есть другая схема, приложение
остановится, не меняя таблицу.

Схемы, использовавшиеся до версии `0.1.0`, не поддерживаются и автоматически не мигрируют.

Длинный период обрабатывается по одному дню. Если один из дней завершился с ошибкой, предыдущие дни
уже сохранены, а проблемный день не записан. В логе будет дата, с которой можно продолжить выгрузку,
указав её в `OZON_DATE_FROM`.

## Автоматический запуск

Для разового запуска из планировщика используйте:

```console
cd /opt/ozon_to_google_sheets
docker compose run --rm --pull always app
```

Пример для cron — каждый день в 06:15 по часовому поясу сервера:

```cron
15 6 * * * cd /opt/ozon_to_google_sheets && /usr/bin/docker compose run --rm --pull always app >> logs/cron.log 2>&1
```

Минимальные unit-файлы systemd:

```ini
# /etc/systemd/system/ozon-to-google-sheets.service
[Unit]
Description=Export Ozon accruals to Google Sheets
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/ozon_to_google_sheets
ExecStart=/usr/bin/docker compose run --rm --pull always app
```

```ini
# /etc/systemd/system/ozon-to-google-sheets.timer
[Unit]
Description=Run Ozon to Google Sheets daily

[Timer]
OnCalendar=*-*-* 06:15:00
Persistent=true
Unit=ozon-to-google-sheets.service

[Install]
WantedBy=timers.target
```

```console
sudo systemctl daemon-reload
sudo systemctl enable --now ozon-to-google-sheets.timer
```

Если `command -v docker` показывает другой путь, замените `/usr/bin/docker` в примерах на него.

Не запускайте две синхронизации одного листа одновременно. В рамках одной установки приложение
использует файл блокировки в `logs/`: второй запуск завершится с кодом `1`. Установки на разных
серверах или с разными каталогами `logs/` не видят блокировки друг друга, поэтому для одного листа
должен работать один планировщик.

## Права на сервере

Для локального запуска файлы могут принадлежать пользователю, который запускает приложение. В
Docker процесс работает от UID/GID `10001`.

```console
chmod 750 .
chmod 600 .env
sudo chown -R 10001:10001 secrets logs
sudo chmod 700 secrets
sudo chmod 600 secrets/google-service-account.json
sudo chmod 750 logs
```

Контейнеру нужен доступ на чтение к `secrets/google-service-account.json` и на запись к `logs/`.
Остальным файлам достаточно обычных прав `644`, директориям — `755`. Не используйте `chmod 777`.

## Безопасность

- не добавляйте `.env` и JSON-ключ Google в Git;
- выдавайте Ozon-ключу минимальные права;
- открывайте сервисному аккаунту только нужную таблицу;
- если ключ попал в Git или чат, сразу отзовите его и создайте новый.

## Если что-то не работает

| Ошибка | Что проверить |
| --- | --- |
| `Missing required environment variables` | Обязательные значения в `.env` |
| `Set exactly one of ...` | Оставлен только один способ передачи Google credentials |
| Google 403 | Включён Sheets API, а `client_email` добавлен в таблицу как редактор |
| Лист не найден | В `GOOGLE_WORKSHEET_ID` указан числовой `gid`, а не название вкладки |
| `Unexpected header` | Первая строка листа соответствует ожидаемой схеме или лист пустой |
| Ozon 401/403 | Client ID, API-ключ и права ключа |
| Ozon 429/5xx | Повторите запуск позже; приложение само делает до трёх попыток |
| `Permission denied` в Docker | UID/GID `10001` читает `secrets` и пишет в `logs` |
| `Another synchronization is already running` | Дождитесь завершения текущего запуска; проверьте cron и systemd на дублирующиеся задания |

Если необходимо отправить куда-либо логи работы приложения, удалите из них токены, ключи,
ID продавца и данные покупателей.

## Разработка

Локальное воспроизведение Python-части CI:

```console
uv sync --locked --python 3.10
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest
uv build
```

Повторите этот блок с `--python 3.14`: CI проверяет нижнюю и верхнюю заявленные версии Python.
Тесты работают без доступа к Ozon и Google.

Проверка установки собранного wheel в чистое окружение:

```console
package_environment="$(mktemp -d)/venv"
uv venv --python 3.14 "$package_environment"
uv pip install --python "$package_environment/bin/python" dist/*.whl
"$package_environment/bin/python" -c "import ozon_to_google_sheets"
test -x "$package_environment/bin/ozon-to-google-sheets"
```

Проверка конфигурации Compose:

```console
OZON_ENV_FILE=.env.example docker compose config --quiet
```

Для каждого pull request и push в `develop` или `main` CI запускает Python-проверки и проверяет
конфигурацию Compose. Тесты требуют покрытия не ниже 95%: падение ниже порога останавливает CI.
Остальные проверки и публикация контейнера описаны в workflow CI.

## Помощь и поддержка

Можем помочь на коммерческой основе развернуть проект на вашем сервере или сделать всё
«под ключ» — поднять инфраструктуру, развернуть и администрировать проект. Обращайтесь:

- Telegram: [@sotchenkov](https://t.me/sotchenkov)
- Email: [sotchenkoff@gmail.com](mailto:sotchenkoff@gmail.com)

Поддержать проект:

[![CloudTips](https://img.shields.io/badge/CloudTips-Поддержать-008BFF?style=for-the-badge)](https://pay.cloudtips.ru/p/61fd42cb)

## Лицензия

Проект распространяется по [Elastic License 2.0](LICENSE).

**Если коротко:**

- можно бесплатно использовать и менять код для себя или своей компании;
- можно за деньги развернуть проект на сервере клиента для его собственного использования;
- нельзя без отдельной лицензии предоставлять клиентам доступ к существенной функциональности
  проекта как к размещённому или управляемому сервису (например, SaaS);
- для такого использования можно купить коммерческую лицензию у автора.

Полные условия находятся в [LICENSE](LICENSE).

ПО предоставляется «как есть», без гарантий. Автор не отвечает за ущерб, возникший из-за
использования приложения, включая ошибки или расхождения в выгруженных данных. Сверяйте результат
с финансовыми отчётами Ozon.

Copyright © 2026 Alexey Sotchenkov.
