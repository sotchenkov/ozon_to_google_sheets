# ozon_to_google_sheets

## Tests

Install the locked project and development dependencies, then run the complete offline suite:

```console
uv sync --locked
uv run pytest
```

`pytest` uses anonymized JSON fixtures and in-memory HTTP and Google Sheets fakes. It requires
neither network access nor seller credentials, and enforces at least 95% statement and branch
coverage. Run the lint checks with:

```console
uv run ruff check tests src
```
