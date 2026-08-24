<div align="center">

# Ozon → Google Sheets

**Выгрузка финансовых начислений Ozon в Google Sheets**

**Русский** · [English](README.en.md)

[![CI](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml/badge.svg)](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml)
[![Coverage 98%](https://img.shields.io/badge/coverage-98%25-brightgreen?style=flat-square)](pyproject.toml)
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

Контейнер загрузит начисления в выбранный лист и завершится. Заголовки займут строку `A1:T1`,
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

## Пример таблицы

| ID операции | Дата начисления | Тип начисления | Номер отправления или идентификатор услуги | SKU | Количество | За продажу или возврат до вычета комиссий и услуг | Ставка комиссии | Комиссия за продажу | Сборка заказа | Обработка отправления | Магистраль | Последняя миля | Обратная магистраль | Обработка возврата | Обработка отменённого или невостребованного товара | Обработка невыкупленного товара | Логистика | Обратная логистика | Итого |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 910001 | 2026-01-15 | POSTING | posting-demo-0001 | 900000001 | 3 | 100,00 | 10% | -10,00 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 90,00 |

Для начисления с несколькими SKU создаётся несколько строк. «Итого» заполняется только в первой,
чтобы при суммировании столбца начисление учитывалось один раз.

## Повторные запуски

Проект можно запускать повторно: уже загруженные операции обновятся, новые
добавятся, а операции за другие даты останутся на месте. Ручные изменения в листе
выгрузки могут быть перезаписаны, поэтому формулы и комментарии лучше держать на отдельном
листе.

Если лист пустой, заголовки добавятся автоматически. Если в первой строке уже есть другая схема,
приложение остановится, не меняя таблицу.

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

Если необходимо отправить куда-либо логи работы приложения, удалите из них токены, ключи,
ID продавца и данные покупателей.

## Разработка

```console
uv sync --locked --python 3.14
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest
```

Тесты работают без доступа к Ozon и Google. CI запускает форматирование, lint, тесты и сборку
пакета. Для pull request также собирается и проверяется Docker image.

Сборка пакета:

```console
uv build
```

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
- нельзя без отдельной лицензии сделать публичный SaaS или managed service на основе проекта;
- для SaaS или managed service можно купить коммерческую лицензию у автора.

Полные условия находятся в [LICENSE](LICENSE).

Copyright © 2026 Alexey Sotchenkov.
