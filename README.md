# ozon_to_google_sheets

## Local CI checks

Install the locked project with the Python version used by CI, then run formatting, lint, and the
complete offline test suite:

```console
uv sync --locked --python 3.14
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest
```

`pytest` uses anonymized JSON fixtures and in-memory HTTP and Google Sheets fakes. It requires
neither network access nor seller credentials, and enforces at least 95% statement and branch
coverage.

Build both package distributions and verify the wheel in a clean environment:

```console
uv build
package_environment="$(mktemp -d)/venv"
uv venv --python 3.14 "$package_environment"
uv pip install --python "$package_environment/bin/python" dist/*.whl
"$package_environment/bin/python" -c "import ozon_to_google_sheets"
```

Build and scan the same container target as CI (Trivy must be installed locally):

```console
docker build --platform linux/amd64 --tag ozon-to-google-sheets:ci-local .
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 \
  ozon-to-google-sheets:ci-local
```

## Run with Docker Compose

Copy `.env.example` to `.env`, replace every placeholder, and place the Google service-account
file at `secrets/google-service-account.json`. Create a local `logs` directory for persistent
application logs. On Linux, make it writable by the container user with UID and GID `10001`.
The local `logs` directory is mounted read-write at `/app/logs`, while `secrets` is mounted
read-only at `/app/secrets`. Both directories are ignored by Git and are never included in the
image.

Run the one-shot synchronization from the GHCR image with:

```console
docker compose up --pull always --abort-on-container-exit --exit-code-from app
docker compose down
```

If the GHCR package is private, authenticate Docker with a token that has only `read:packages`
before starting Compose. Set `OZON_ENV_FILE` to use an environment file other than `.env`.

## CI and container tags

Pull requests into `develop` or `main` run all Python checks, build the container without
publishing it, and fail on high or critical vulnerabilities. A push to `develop` runs the Python
checks only. After a merge into `main`, CI builds one container, scans it, and publishes that same
verified image to GitHub Container Registry with both `sha-<commit>` and `latest` tags.

After publication, CI resolves the registry digest and opens a pull request into `develop` that
pins the Compose `image` value to `sha-<commit>@sha256:<digest>`.

Consequently, `latest` never points at code that exists only in `develop`. Consumers that require
an immutable version should use the `sha-<commit>` tag (or the registry digest) instead of
`latest`.

Repository rulesets should block direct pushes to `develop` and `main`, require pull-request
approval, and require the `Python quality and package` and `Container build and scan` checks before
merge. Repository Actions settings must allow GitHub Actions to create pull requests so the image
digest update can use the same protected flow. The workflow contains no deployment, release, or
user-managed secrets.
