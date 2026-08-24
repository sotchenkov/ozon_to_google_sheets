<div align="center">

# Ozon → Google Sheets

**Export Ozon financial accruals to Google Sheets**

[Русский](README.md) · **English**

[![CI](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml/badge.svg)](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml)
[![Coverage 98%](https://img.shields.io/badge/coverage-98%25-brightgreen?style=flat-square)](pyproject.toml)
[![Python 3.10–3.14](https://img.shields.io/badge/Python-3.10%E2%80%933.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![License: Elastic 2.0](https://img.shields.io/badge/license-Elastic%202.0-005571?style=flat-square)](LICENSE)

[Run](#quick-start) · [Credentials](#credential-setup) ·
[Sheet](#example-sheet) · [Support](#help-and-support)

</div>

The application reads financial accruals from the Ozon Seller API and writes them to Google
Sheets.

## Quick start

You need Docker with Compose v2, an Ozon Seller API key, a Google spreadsheet, and a Google service
account JSON key.

### 1. Prepare the files

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

See [Credential setup](#credential-setup) for instructions on creating the keys and sharing the
spreadsheet.

### 2. Fill in `.env`

```dotenv
OZON_TOKEN=replace-with-ozon-api-token
OZON_CLIENT_ID=replace-with-ozon-client-id
GOOGLE_CREDENTIALS_PATH=secrets/google-service-account.json
GOOGLE_SPREADSHEET_ID=replace-with-google-spreadsheet-id
GOOGLE_WORKSHEET_ID=0

# Optional date range in YYYY-MM-DD format
# OZON_DATE_FROM=2026-01-01
# OZON_DATE_TO=2026-01-31
```

Every value in the example is a placeholder.

### 3. Run

On a Linux server, first grant the container access to [`secrets/` and `logs/`](#server-permissions).

```console
docker compose up --pull always --abort-on-container-exit --exit-code-from app
docker compose down
```

The container loads the accruals into the selected worksheet and exits. The header is written to
`A1:T1`, with data below it. Warnings and errors go to `logs/logs.log`.

### Run without Docker

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```console
uv sync --locked --no-dev
uv run --no-sync ozon-to-google-sheets
```

## Credential setup

### Ozon API

1. Open [Ozon Seller](https://seller.ozon.ru/) and go to the Seller API settings.
2. Copy the **Client ID** and use it as `OZON_CLIENT_ID`.
3. Create an API key with access to financial data and use it as `OZON_TOKEN`.
4. If several roles are available, choose the minimum read-only role.

Dashboard labels may change. See the current
[Ozon Seller API documentation](https://docs.ozon.ru/api/seller/).

### Google service account

1. Create or select a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Google Sheets API**.
3. Open **IAM & Admin → Service Accounts** and create a service account.
4. Open the account and select **Keys → Add key → Create new key → JSON**.
5. Save the downloaded file as `secrets/google-service-account.json`.
6. Open the target Google spreadsheet, select **Share**, and add the address from the JSON
   `client_email` field with the **Editor** role.

The spreadsheet does not need to be public, and the service account does not need a project-level
IAM role.

Official Google guides:
[create credentials](https://developers.google.com/workspace/guides/create-credentials) and
[manage JSON keys](https://cloud.google.com/iam/docs/keys-create-delete).

### Spreadsheet and worksheet IDs

Open the target spreadsheet in a browser. Given this URL:

```text
https://docs.google.com/spreadsheets/d/1AbCdEfGhExample/edit#gid=123456789
```

- `GOOGLE_SPREADSHEET_ID=1AbCdEfGhExample` is the value between `/d/` and `/edit`;
- `GOOGLE_WORKSHEET_ID=123456789` is the number after `gid=`.

The application does not create a spreadsheet or worksheet; prepare them first.

## Configuration

| Variable | Purpose |
| --- | --- |
| `OZON_TOKEN` | Ozon Seller API key |
| `OZON_CLIENT_ID` | Seller Client ID |
| `GOOGLE_SPREADSHEET_ID` | Google spreadsheet ID |
| `GOOGLE_WORKSHEET_ID` | Numeric worksheet `gid` |
| `GOOGLE_CREDENTIALS_PATH` | Path to the Google JSON key; recommended option |
| `GOOGLE_CREDENTIALS_JSON` | Full JSON key supplied by an external secret store |
| `OZON_DATE_FROM` | Start date, `YYYY-MM-DD` |
| `OZON_DATE_TO` | End date, `YYYY-MM-DD` |
| `OZON_ENV_FILE` | Another Docker Compose env file instead of `.env` |

Set only one Google credentials source: `GOOGLE_CREDENTIALS_PATH` or
`GOOGLE_CREDENTIALS_JSON`. Process environment variables take precedence over `.env`.

### Date range

Both boundaries are included. Dates use the `Europe/Moscow` timezone.

| `OZON_DATE_FROM` | `OZON_DATE_TO` | Exported dates |
| --- | --- | --- |
| not set | not set | Yesterday and today |
| set | not set | From the specified date through today |
| not set | set | The specified date only |
| set | set | The entire specified range |

Dates must be between `2022-01-01` and today. The start date cannot be later than the end date.

## Example sheet

The application writes the following Russian column names:

| ID операции | Дата начисления | Тип начисления | Номер отправления или идентификатор услуги | SKU | Количество | За продажу или возврат до вычета комиссий и услуг | Ставка комиссии | Комиссия за продажу | Сборка заказа | Обработка отправления | Магистраль | Последняя миля | Обратная магистраль | Обработка возврата | Обработка отменённого или невостребованного товара | Обработка невыкупленного товара | Логистика | Обратная логистика | Итого |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 910001 | 2026-01-15 | POSTING | posting-demo-0001 | 900000001 | 3 | 100.00 | 10% | -10.00 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 90.00 |

An accrual with multiple SKUs produces multiple rows. The total is written only to the first row,
so summing the column counts the accrual once.

## Repeated runs

You can run the project repeatedly: existing operations are updated, new ones are appended, and
operations for other dates remain in the worksheet. Manual edits in the export worksheet may be
overwritten, so keep formulas and comments in a separate worksheet.

An empty worksheet receives the header automatically. If its first row already contains another
schema, the application stops without changing the worksheet.

## Server permissions

For a local run, files may belong to the user running the application. In Docker, the process runs
under UID/GID `10001`.

```console
chmod 750 .
chmod 600 .env
sudo chown -R 10001:10001 secrets logs
sudo chmod 700 secrets
sudo chmod 600 secrets/google-service-account.json
sudo chmod 750 logs
```

The container needs read access to `secrets/google-service-account.json` and write access to
`logs/`. The default `644` for other files and `755` for directories is sufficient. Do not use
`chmod 777`.

## Security

- do not add `.env` or the Google JSON key to Git;
- give the Ozon key the minimum required permissions;
- share only the required spreadsheet with the service account;
- if a key is exposed through Git or chat, revoke it immediately and create a new one.

## Troubleshooting

| Error | What to check |
| --- | --- |
| `Missing required environment variables` | Required values in `.env` |
| `Set exactly one of ...` | Only one Google credentials method is configured |
| Google 403 | Sheets API is enabled and `client_email` is an Editor of the spreadsheet |
| Worksheet not found | `GOOGLE_WORKSHEET_ID` contains the numeric `gid`, not the tab name |
| `Unexpected header` | The first row matches the expected schema or the worksheet is empty |
| Ozon 401/403 | Client ID, API key, and key permissions |
| Ozon 429/5xx | Retry later; the application already makes up to three attempts |
| Docker `Permission denied` | UID/GID `10001` can read `secrets` and write to `logs` |

If you need to share application logs, remove tokens, keys, seller IDs, and customer data first.

## Development

To reproduce the Python part of CI locally:

```console
uv sync --locked --python 3.10
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest
uv build
```

Repeat this block with `--python 3.14`: CI tests the lowest and highest supported Python versions.
Tests run without access to Ozon or Google.

To verify the built wheel in a clean environment:

```console
package_environment="$(mktemp -d)/venv"
uv venv --python 3.14 "$package_environment"
uv pip install --python "$package_environment/bin/python" dist/*.whl
"$package_environment/bin/python" -c "import ozon_to_google_sheets"
test -x "$package_environment/bin/ozon-to-google-sheets"
```

Compose and container checks require Docker Buildx; building a foreign architecture also requires
QEMU. Trivy must be available as the `trivy` command:

```console
OZON_ENV_FILE=.env.example docker compose config --quiet
docker buildx build --platform linux/amd64 --load -t ozon-to-google-sheets:ci-amd64 .
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 ozon-to-google-sheets:ci-amd64
docker buildx build --platform linux/arm64 --load -t ozon-to-google-sheets:ci-arm64 .
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 ozon-to-google-sheets:ci-arm64
```

CI runs the Python checks and `docker compose config` for every pull request. Both architectures are
built and scanned only for pull requests targeting `main`. After a merge to `main`, CI checks
`linux/amd64` and `linux/arm64` again; the `sha-*` and `latest` tags move only after both Trivy scans
succeed. A separate pull request then pins the verified digest in the `develop` branch's
`docker-compose.yml`.

## Help and support

We offer commercial help with deploying the project on your server or delivering everything
turnkey: infrastructure setup, deployment, and administration. Contact us:

- Telegram: [@sotchenkov](https://t.me/sotchenkov)
- Email: [sotchenkoff@gmail.com](mailto:sotchenkoff@gmail.com)

Support the project:

[![CloudTips](https://img.shields.io/badge/CloudTips-Support-008BFF?style=for-the-badge)](https://pay.cloudtips.ru/p/61fd42cb)

## License

The project is distributed under the [Elastic License 2.0](LICENSE).

**In short:**

- you may use and modify the code free of charge for yourself or your company;
- you may charge a client to deploy the project on their server for their own use;
- you may not create a public SaaS or managed service from the project without a separate license;
- a commercial license is available from the author for SaaS or managed-service use.

See [LICENSE](LICENSE) for the full terms.

Copyright © 2026 Alexey Sotchenkov.
