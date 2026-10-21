# Textile Quality Intelligence

A local-first web application for recording textile quality inspections, defects, product
disposition and corrective actions, and for reviewing the results in reports. It runs on
your own computer; no data leaves the machine and no internet connection is needed after
installation.

**Stack:** Python 3.12, Flask 3, Jinja, plain CSS and a little vanilla JavaScript, SQLite via
SQLAlchemy 2, Alembic migrations (Flask-Migrate), pytest, Ruff.

> **Status:** see [Verification status](#verification-status). The business rules and page
> templates are covered by automated tests that were run; the database-backed layers are
> covered by tests that you must run on your own machine (instructions below).

## What it does

| Area | Capabilities |
| --- | --- |
| Inspections | Record date, product, batch, stage/type, inspector, inspected quantity and unit; defects can be entered on the same form; search and filter; edit; delete (only when nothing depends on it) |
| Defects | Your own defect categories and severity labels (nothing is preset); defect entries with quantity, unit, suspected cause, observations; add/edit/delete |
| Disposition | One record per inspection: accepted + rework + rejected + pending must equal the inspected quantity exactly. A missing record is shown as "not recorded", never as "all accepted" |
| Corrective actions | Problem, suspected vs confirmed root cause, owner, target date, status workflow, follow-up assessments. Completion is not effectiveness: "Effective"/"Not effective" require a recorded follow-up. Actions without a target date are never overdue |
| Reports | Inspection summary, defect analysis, disposition, trend (day/week/month), corrective actions. Every report lists its filters. Units are never added together; rates show "Not applicable" when the denominator is zero |
| Data | Database status, verified one-click backup, command-line restore |

Rules chosen where the specification left a decision open are listed under
[Design decisions](#design-decisions).

## Windows setup (Command Prompt)

Requires Python 3.12 (3.11-3.13 should also work) from <https://www.python.org/downloads/>.
Tick "Add python.exe to PATH" during installation.

```bat
cd textile-quality-intelligence
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
flask --app run db upgrade
python run.py
```

Then open <http://127.0.0.1:5000> in your browser. Stop the server with `Ctrl+C`.

Optional: add illustrative starter categories/severity labels (edit them afterwards to match
your own procedures):

```bat
flask --app run seed-reference
```

The database is created at `instance\textile_quality.db`. To use another location set
`TQI_DATABASE_PATH` (see `.env.example`; `set TQI_DATABASE_PATH=C:\data\tqi.db` in CMD).

### macOS / Linux

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
flask --app run db upgrade
python run.py
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `TQI_ENV` | `development` | `development`, `testing` or `production` |
| `TQI_SECRET_KEY` | auto-generated in `instance/.secret_key` (development only) | Required when `TQI_ENV=production` |
| `TQI_DATABASE_PATH` | `instance/textile_quality.db` | SQLite file |
| `TQI_DEBUG` | `0` | `1` enables Flask debug mode (development only) |
| `TQI_PORT` | `5000` | Port (the server only listens on 127.0.0.1) |
| `TQI_LOG_LEVEL` | `INFO` | Python logging level |

## Tests and checks

```bat
pip install -r requirements-dev.txt
pytest
ruff check .
```

* `tests\unit` - business rules (validation, disposition reconciliation, workflow
  transitions, metrics), configuration, backup/restore, and rendering of every page template.
* `tests\integration` - the database-backed behaviour: atomic saves and rollback,
  foreign-key enforcement, restricted deletes, workflow, report figures against a
  hand-computed dataset, CSRF, escaping of user text, persistence after reopening the
  database, and that the Alembic migration produces exactly the schema the models describe.

## Backup and restore

* **Backup:** Data Management page -> "Create backup now", or `flask --app run backup`.
  Backups are written to `instance\backups\` using SQLite's backup API, integrity-checked, and
  never overwrite an earlier file.
* **Restore:** stop the application, then
  `flask --app run restore-backup "instance\backups\tqi-backup-YYYYMMDD-HHMMSS.db"`.
  The backup is validated first; your current database is kept as
  `textile_quality.db.pre-restore-<timestamp>`.
* `flask --app run db-status` shows file size, integrity and schema state.

## Project layout

```
app/
  __init__.py           application factory
  config.py             environment-based configuration
  domain/               pure business rules (no Flask / database imports)
  models/               SQLAlchemy models
  services/             database operations and report queries
  routes/               Flask blueprints (thin: parse request, call service, render)
  templates/, static/   Jinja templates, CSS, small JS
migrations/             Alembic environment and 0001_initial schema
tests/unit, tests/integration
run.py                  start the local server
```

## Design decisions

* **Quantities are whole numbers**, so reconciliation has no rounding. Units are free text
  (suggestions: pieces, meters, yards, kg), stored lower-case; defect and disposition units
  must match their inspection's unit.
* **Disposition is one reconciled record per inspection.** Multi-stage outcomes such as
  "reworked then accepted" are not modelled.
* **Defect entries are findings, not defective items.** Reports show the count of entries and
  the sum of quantities separately and never mix units.
* **Severity and categories carry no built-in meaning** or acceptance limits; they are labels
  you define.
* **Corrective-action completion date is a date entered by the user**, not an automatic
  timestamp.
* **No authentication or roles.** This is a single-user local tool bound to 127.0.0.1. Do not
  expose it to a network.
* **Restore is command-line only**, because replacing a live database from a web page is unsafe.
* **Deletes are restricted:** an inspection with defects, a disposition or actions cannot be
  deleted; reference data that is in use is deactivated instead.

## Known limitations

* No login, user accounts, audit trail, or multi-user concurrency control.
* No import/export of CSV or Excel, no charts, no printing layout beyond the browser's.
* No acceptance-sampling plans, AQL or standards-based decisions; no photos or attachments.
* Timestamps are stored in UTC and shown as such.
* SQLite is intended for one local user and modest data volumes.
* Windows was the target platform; other platforms should work but were not a focus.

## Verification status

What was actually run when this version was produced (in a sandbox that had Flask but could
not install SQLAlchemy, Flask-SQLAlchemy, Flask-Migrate or Flask-WTF):

* Passed: unit tests for the domain rules, configuration, backup/restore (real SQLite files) and
  rendering of all 16 templates with sample data under strict undefined-variable checking
  (76 tests); Ruff; Python byte-compilation of all modules.
* **Not run there:** the SQLAlchemy models and queries, the Alembic migration, the routes
  against a real database, and the integration tests. These are written but unverified until you
  run `pytest` after installing the requirements. If something fails, the failure message
  identifies the exact area.

## Publishing to GitHub (account `vipintk2807`)

You use several GitHub accounts, so check identity before pushing. Nothing here changes any
other account's configuration.

```bat
cd textile-quality-intelligence
git init -b main
git config --local user.name "Vipin T K"
git config --local user.email "<the email you use for this GitHub account>"
git config --get user.name
git config --get user.email
git status
git remote -v
```

Confirm `git status` does not list `instance\*.db`, `.env`, `instance\.secret_key`, `.venv` or any
private planning documents (they are in `.gitignore`). Then verify the SSH alias, if you have
created one for this account:

```bat
ssh -T git@github-vipintk2807
```

It should greet `vipintk2807`. If the alias does not exist yet, create it in your SSH config
first (or use HTTPS and sign in through Git Credential Manager). Never paste tokens or
passwords into commands or files. Create the empty repository `textile-quality-intelligence` on
GitHub under `vipintk2807`, then:

```bat
git remote add origin git@github-vipintk2807:vipintk2807/textile-quality-intelligence.git
git add .
git status
git commit -m "Initial commit: Textile Quality Intelligence"
git branch --show-current
git push -u origin main
```

If `git remote -v` already shows an `origin`, check it points at the repository above before
changing it (`git remote set-url origin ...`).

## Licence

MIT - see `LICENSE`.
