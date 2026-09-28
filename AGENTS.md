# Repository Guidelines

## Project Structure & Module Organization

- `src/` contains the application: `entry.py` exposes Worker entrypoints, `app.py` configures FastAPI/CORS, `api.py` and `ui.py` define routes, `domain.py` holds rules, `db.py` handles D1, and `email_import.py` parses BCA messages.
- `tests/` contains unit, in-process integration, and Worker smoke tests. Shared fixtures and the SQLite D1 adapter are in `tests/conftest.py` and `tests/fake_d1.py`.
- `migrations/` stores historical D1 changes; `db_init.sql` is the current fresh-database schema and seed. Optional demo data is under `seeds/`.
- `specs/` documents feature contracts; `docs/` contains operations notes. Wrangler environments and bindings live in `wrangler.jsonc`.

## Build, Test, and Development Commands

Run from the repository root:

```powershell
uv sync                              # Install Python dependencies
npm install                          # Install Wrangler
uv run pywrangler dev --port 8787   # Start the default Worker locally
uv run pytest                        # Run the default test suite
uv run pytest -m unit                # Run fast unit tests only
uv run pytest --cov=src --cov-report=term-missing
```

Use `npm run dev` for the default Worker. Worker smoke tests (`uv run pytest -m worker`) start PyWrangler and require the selected D1 binding to use `"remote": false`; they may write local data. Deploy with `uv run pywrangler deploy`, adding `--env private` for the private Worker.

## Coding Style & Naming Conventions

Use Python 3.12-compatible code with four-space indentation, `snake_case` functions/variables, `PascalCase` classes/models, and annotations. Keep handlers thin, rules in `domain.py` or models, and database access in `db.py`. Follow existing JSON and route conventions. No formatter or linter is configured; run tests.

## Testing Guidelines

Name tests `test_<behavior>` and place them in `tests/unit/` or the matching integration file. Mark tests `unit`, `integration`, or `worker` when appropriate. Add regression coverage for validation, balance/report calculations, migrations, and email-import edge cases. The default suite excludes `worker` tests.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects matching project history, such as `Add ...`, `Revise ...`, or `Fix ...`; keep each commit focused. Pull requests should explain the behavior change, identify affected routes/schema/configuration, include tests run, and call out any D1 or Wrangler setup required. Include screenshots for UI changes and mention migration or deployment considerations explicitly.

## Security & Configuration Tips

Never commit credentials or real financial emails. Treat Wrangler bindings as environment-specific: verify whether commands target local or remote D1 before running writes. The application currently has no authentication or per-user isolation, so do not expose a deployed Worker without reviewing that risk.
