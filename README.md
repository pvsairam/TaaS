# Quartermaster (working title) — TaaS

AI-assisted regression testing that certifies each **Oracle Fusion Cloud quarterly update**
(A/B/C/D releases) before it reaches production.

> Core idea: **deterministic core, AI at the edges.** Tests are replayable YAML specs run by a
> Playwright/REST engine. AI ranks release impact, drafts tests, proposes locator heals and
> triages failures. Every AI output is validated and reviewable.

**Build order:** HCM first, then ERP, then SCM. Product model: commercial multi-tenant SaaS
that is also used internally.

The full product and architecture plan (market analysis, architecture, roadmap, risks, open
questions and name ideas) is in **[docs/PLAN.md](docs/PLAN.md)**.

## What works today (Phase 0)

| Area | Module |
|---|---|
| Domain model (releases, features, tests, locators, results) | `src/quartermaster/domain/models.py` |
| YAML test DSL + validation (placeholders, duplicate ids, strict fields) | `src/quartermaster/dsl/loader.py` |
| Release impact analysis + time-budgeted regression planner (explainable) | `src/quartermaster/impact/analyzer.py` |
| Multi-strategy locator resolution with fallback self-healing | `src/quartermaster/locators/resolver.py` |
| Step engine with evidence capture, skip-on-failure, AI healer hook | `src/quartermaster/runner/engine.py` |
| Playwright driver for Fusion (**Phase 1, partial**) | `src/quartermaster/runner/playwright_driver.py` |
| Production guard (blocks PROD kind and prod-looking pod hosts) | `src/quartermaster/safety/guards.py` |
| Claude-backed test author + failure triage, with PII masking | `src/quartermaster/ai/` |
| Per-persona credentials from environment variables; `login_as` persona switching | `src/quartermaster/runner/credentials.py` |
| Record and playback: `qm record` captures clicks/typing into a YAML spec | `src/quartermaster/recorder/` |
| Evidence per run: screenshots (off / on failure / every step), video, `run.json`, Word document | `src/quartermaster/evidence/` |
| `qm` CLI (`validate`, `plan`, `run`, `record`, `document`) | `src/quartermaster/cli.py` |

## Quick start

```bash
pip install -e ".[dev]"          # add ,ai for Claude, ,browser for Playwright
pytest -q

qm validate examples/tests
qm plan --release examples/releases/26D_sample.json --tests examples/tests --budget 25 --explain
```

## Writing a test

```yaml
id: ap.create-invoice-po-match
title: Create and validate a PO-matched supplier invoice
module: Financials
product: Payables
priority: critical
data:
  invoice_number: QM-INV-${RUN_ID}   # RUN_ID is unique per run
steps:
  - action: navigate
    intent: Open Invoices work area
    value: Payables > Invoices
  - action: fill
    intent: Enter invoice number
    value: ${invoice_number}
    target:
      strategies:            # tried in order; first unique match wins
        - label: Number
        - label: Invoice Number
```

See `examples/tests/hcm/` and `examples/tests/erp/` for complete specs. The absence example shows
an employee submitting a request and switching to the line manager (`login_as`) to approve it.

## Run it on your own computer (fastest way to reach your pod)

If your laptop can open the pod in a browser, it can run Quartermaster. You need Python 3.11+
and Git.

```bash
git clone https://github.com/pvsairam/TaaS.git && cd TaaS
git checkout claude/awesome-bardeen-r668wx
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[browser]"
python -m playwright install chromium
```

Set the connection details for this terminal only (don't save them in the repo):

```bash
# Windows PowerShell                                        # macOS/Linux
$env:QM_FUSION_URL="https://<pod>.fa.us6.oraclecloud.com"   # export QM_FUSION_URL=...
$env:QM_FUSION_USER="<user>"                                # export QM_FUSION_USER=...
$env:QM_FUSION_PASSWORD="<password>"                        # export QM_FUSION_PASSWORD=...
```

Then:

```bash
qm run examples/smoke/login.yaml --headed        # 1. can we sign in?
qm run examples/tests/hcm/view_worker.yaml --headed

# Record your own test: a browser opens already signed in; click through the flow, then press
# "Stop recording" in the page (or Enter in the terminal). Replay it any time, e.g. every quarter.
qm record my_tests/view_worker.yaml --id hcm.view-worker --title "View a worker" \
  --module HCM --product "Global Human Resources"
qm run my_tests/view_worker.yaml --headed
```

While recording, a small toolbar sits at the bottom right of the page:

- **Add check**: the next click records a check instead of an action. Click a value (for example
  the City a postal code filled in) and the replay will fail if that value is different. Add at
  least one check at the end of every flow, so a replay proves the outcome, not only the clicks.
- **Stop recording**: saves the test file and closes the browser.

What gets recorded, and how it replays:

| You do | Saved as |
|---|---|
| Open a page from the Navigator (☰, expand a group, click an item) | one step: `navigate: My Client Groups > Workforce Structures` |
| Click a button, link or tile | `click` |
| Type in a field, or type a Redwood date | `fill` (dates as `01/01/1951`) |
| Type in a list and click a suggestion | `select`, with the exact suggestion kept as `pick` |
| Add check, then click a value | `assert_text` (or `assert_visible` for long text) |

Typed and checked values go into the file's `data` block (`value1`, `value2`...), so you can change
test data without touching the steps; rename them to something meaningful. Sign-in and password
fields are never recorded, and Oracle's generated ids are not used as locators because they change.
When a label appears more than once on a page (City in the address and again in tax details), the
step is anchored to the section heading above it.

Keep recorded tests in one folder under version control (for example `my_tests/`) and re-run the
folder after each quarterly update: `qm run my_tests --evidence-doc`. Only keep tests there that
are safe to repeat.

## Proof of testing: screenshots, video and the Word evidence document

Choose per run what to capture:

```bash
qm run examples/tests/hcm/create_location.yaml --screenshots every-step --video always \
  --evidence-doc --release 26C --tester "Your Name"
```

| Option | Values |
|---|---|
| `--screenshots` | `off`, `on-failure` (default), `every-step` |
| `--video` | `off` (default), `on-failure` (kept only when the run fails), `always` |
| `--evidence-doc` | write the Word evidence document |
| `--release`, `--tester` | shown in the evidence; tester defaults to your login name |

Each run gets its own folder:

```
evidence/<test id>/<run id>/
  run.json                              what ran, where, by whom, and every step's result
  screenshots/step-01.png ...           the browser window after each step, element boxed in red
  videos/*.webm                         only when video is on; never put in the document
  <test id>_<run id>_evidence.docx      only with --evidence-doc
```

The Word document has a cover with the run details, a step summary, then one page per step
with the description, value used, expected result (the optional `expected:` field on a step),
actual result, time and screenshot, and a sign-off table at the end. Each screenshot and the
test file carry a SHA-256 fingerprint in `run.json` and the document, so a reviewer can check
nothing was swapped. Screenshots of HR screens contain personal data: store the evidence
folders where only the right people can read them.

Rebuild a document from a saved run at any time: `qm document evidence/<test id>/<run id>`.

## Connecting to a Fusion test environment

Credentials are read from environment variables and never go in specs or Git:

| Variable | Purpose |
|---|---|
| `QM_FUSION_URL` | Non-prod pod URL, e.g. `https://xxxx-test.fa.us2.oraclecloud.com` |
| `QM_FUSION_USER` / `QM_FUSION_PASSWORD` | Default test user |
| `QM_FUSION_USER_<PERSONA>` / `QM_FUSION_PASSWORD_<PERSONA>` | Per-persona user, e.g. `QM_FUSION_USER_LINE_MANAGER` |
| `QM_FUSION_KIND` | `DEV`, `TEST` or `STAGE` (default `DEV`) |
| `QM_CHROMIUM_PATH` | Optional path to a preinstalled Chromium |

Then run the login smoke test, followed by the HCM suite:

```bash
pip install -e ".[browser]"
qm run examples/smoke/login.yaml
qm run examples/tests/hcm --report results.json   # failure screenshots go to ./evidence
```

The runner refuses production pods. Use dedicated test users, not real employees' accounts.
