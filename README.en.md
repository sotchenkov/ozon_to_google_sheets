<div align="center">

# Ozon → Google Sheets

**Export Ozon financial accruals to Google Sheets**

[Русский](https://github.com/sotchenkov/ozon_to_google_sheets/blob/main/README.md) · **English**

[![CI](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml/badge.svg)](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml)
[![Coverage ≥95%](https://img.shields.io/badge/coverage-%E2%89%A595%25-brightgreen?style=flat-square)](https://github.com/sotchenkov/ozon_to_google_sheets/actions/workflows/ci.yml)
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
`A1:P1`, with data below it. Warnings and errors go to `logs/logs.log`.

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

### Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | The export completed successfully, including when the period contains no accruals |
| `1` | Ozon, Google Sheets, network, reconciliation, or concurrent-run error |
| `2` | Configuration error or unsupported command-line arguments |

The container returns the application's exit code. The quick-start command propagates it through
`--exit-code-from app`.

## Example sheet

The application writes the following Russian column names:

| ID операции | Дата начисления | Тип начисления | Номер отправления или идентификатор услуги | SKU | Количество | За продажу или возврат до вычета комиссий и услуг | Ставка комиссии | Комиссия за продажу | Последняя миля | Обработка возврата | Обработка отменённого или невостребованного товара | Логистика | Обратная логистика | Прочие или неизвестные начисления | Итого |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 910001 | 2026-01-15 | POSTING | posting-demo-0001 | 900000001 | 2 | 100.00 | 10% | -10.00 | -5.00 | 0 | 0 | -7.00 | 0 | 0 | 123.00 |
| 910001 | 2026-01-15 | POSTING | posting-demo-0001 | 900000002 | 1 | 50.00 | 10% | -5.00 | 0 | 0 | 0 | 0 | 0 | 0 |  |

One Ozon operation may include several SKUs, so its ID appears in several rows. Ozon supplies the
total for the whole operation rather than for each SKU: the application writes it to the first row
and leaves it empty in the others. A normal sum of the column therefore counts the operation once.

### Unknown accruals and reconciliation

Types that do not yet have a dedicated column are stored in `Прочие или неизвестные начисления`
(`Other or unknown accruals`) and produce a warning in the log. The same column receives the
operation amount when Ozon does not provide a monetary breakdown.

Before writing, the application reconciles the sum of every monetary field in an operation with
Ozon's total. If they differ, the current date is not written and the run exits with code `1`.
Review warnings and errors in `logs/logs.log`, then compare the period total with the financial
report in Ozon Seller.

## Repeated runs

You can run the project repeatedly: existing operations are updated, new ones are appended, and
operations for other dates remain in the worksheet. Manual edits in the export worksheet may be
overwritten, so keep formulas and comments in a separate worksheet.

An empty worksheet receives the header automatically even if Ozon returns no accruals. Such a run
is successful. If the first row already contains another schema, the application stops without
changing the worksheet.

A long period is processed one day at a time. If one day fails, earlier days remain saved and the
failing day is not written. The log states the date from which you can resume by setting
`OZON_DATE_FROM`.

## Scheduled runs

Use this one-shot command from a scheduler:

```console
cd /opt/ozon_to_google_sheets
docker compose run --rm --pull always app
```

Example cron entry — every day at 06:15 in the server's timezone:

```cron
15 6 * * * cd /opt/ozon_to_google_sheets && /usr/bin/docker compose run --rm --pull always app >> logs/cron.log 2>&1
```

Minimal systemd units:

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

If `command -v docker` prints another path, replace `/usr/bin/docker` in the examples with it.

Do not run two synchronizations for the same worksheet at once. Within one installation, the
application keeps a lock file in `logs/`, and the second run exits with code `1`. Installations on
different servers or with different `logs/` directories do not share that lock, so use a single
scheduler for each worksheet.

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
| `Another synchronization is already running` | Wait for the active run; check cron and systemd for duplicate jobs |

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

To validate the Compose configuration:

```console
OZON_ENV_FILE=.env.example docker compose config --quiet
```

For every pull request and push to `develop` or `main`, CI runs the Python checks and validates the
Compose configuration. Tests enforce at least 95% coverage: falling below the threshold fails CI.
The remaining checks and container publication are defined in the CI workflow.

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
- without a separate license, you may not give clients access to substantial project functionality
  as a hosted or managed service (for example, SaaS);
- a commercial license is available from the author for such use.

See [LICENSE](LICENSE) for the full terms.

The software is provided “as is”, without warranties. The author is not liable for damages arising
from use of the application, including errors or discrepancies in exported data. Reconcile the
results with Ozon financial reports.

Copyright © 2026 Alexey Sotchenkov.
