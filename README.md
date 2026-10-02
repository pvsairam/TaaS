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

**New here and want to try it?** Follow **[TESTING.md](TESTING.md)**, step by step.

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
| `qm` CLI (`validate`, `plan`, `run`, `record`, `document`, `serve`) | `src/quartermaster/cli.py` |
| Release feature list import (Oracle feature-listing .xlsx, .csv, .json/.yaml) and manual test script import (.xlsx), standard library only | `src/quartermaster/importers/` |
| Web UI on your own computer (`qm serve`): start runs, follow them live, record, open evidence | `src/quartermaster/service/` |

## Start it (no terminal)

On Windows, double-click **Start Quartermaster** in this folder. The first time it installs what it
needs and adds a **Quartermaster** icon to the desktop; after that, double-click the icon. Your
browser opens Quartermaster, and the setup guide asks for the client, its pod and a test user.
**Update Quartermaster** gets the latest version. On Mac or Linux, run `./start-quartermaster.sh`.

## Quick start

```bash
pip install -e ".[dev]"          # add ,ai for Claude, ,browser for Playwright
pytest -q

qm validate examples/tests
qm plan --release examples/releases/26D_sample.json --tests examples/unverified --budget 25 --explain
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

`examples/tests/` holds tests checked against a real pod and safe to repeat (they never submit). More
complete examples are in `examples/unverified/` (HCM and ERP): they are not yet checked against a pod
and they submit real transactions, so they are kept out of the tests folder; see the README there. The
absence example shows an employee submitting a request and switching to the line manager (`login_as`)
to approve it.

### Steps that call a REST API

A step can call a Fusion REST service, for example to check that a record made on the screen is
really saved, or to find an id to open. It uses the browser's signed-in session, so no extra
password is needed, and it only ever calls the pod itself.

```yaml
  - action: api_call
    intent: The new location is saved
    value: GET /hcmRestApi/resources/11.13.18.05/locationsV2?q=LocationName='${location_name}'
    options:
      expect_status: 200            # optional; any 2xx when left out
      check:                        # optional; a path in the JSON reply and the value it must have
        count: 1
        items[0].ActiveStatus: A
        items[0].LocationId: "*"    # "*" means it is there and not empty
      save:                         # optional; later steps can use ${location_id}
        location_id: items[0].LocationId
```

`value` is `METHOD /path` (GET, POST, PATCH, PUT or DELETE). For POST, PATCH and PUT put the JSON to
send under `options.body`; `${name}` placeholders work in it too. A REST step that changes data
changes it on the pod, like a click on Save would.

### Cleaning up after a test

A test that creates something on the pod can remove it again at the end. Put the removal steps under
`cleanup:`. They run after the steps, whether the steps passed or failed.

```yaml
steps:
  - action: api_call
    intent: Create the location
    value: POST /hcmRestApi/resources/11.13.18.05/locationsV2
    options:
      body: {LocationName: "QM Test ${RUN_ID}"}
      save: {location_id: LocationId}       # keep the id of what was made
  # ...more steps that use it...
cleanup:
  - action: api_call
    intent: Remove the location
    value: DELETE /hcmRestApi/resources/11.13.18.05/locationsV2/${location_id}
```

- A cleanup that fails is shown on the run and in the Word document ("Cleanup did not finish: records
  from this test may still be on the pod"). It never changes the test's result, and the other cleanup
  steps still run.
- If the test failed before it made the record, `${location_id}` was never saved. The step is then
  skipped ("Nothing to clean up") instead of calling an address with a blank in it.
- A cleanup `DELETE` must use a saved value such as `${location_id}`. A fixed address is refused when
  the test loads, so a cleanup can only remove what this run made.
- Any step can be a cleanup step (a click, a navigation). Add `options: {needs: location_id}` to skip
  a step when that saved value is missing.

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

## The web UI

Everything above can also be done from web pages on your own computer. In the same terminal where
you set `QM_FUSION_URL`, `QM_FUSION_USER` and `QM_FUSION_PASSWORD`:

```bash
qm serve                          # your tests: my_tests (created on first start from the examples)
```

Your browser opens `http://127.0.0.1:8765`. Keep the terminal open while you use it; Ctrl+C stops it.

| Page | Who it is for | What you do there |
|---|---|---|
| **Overview** | Managers first, everyone | Pass rate, test coverage, what needs attention and runs this week. Release readiness for the pod's Oracle release (passed on it, failed on it, passed only on an earlier release, never passed), a comparison of releases once tests have run on two, recent activity and coverage by module. **Certification pack** downloads a zip for a release: a Word summary to sign (every test's result on that release, what failed, what has not run yet) with each test's evidence document. |
| **Runs** | Testers | Every run with its result, module, release, environment, start, duration, who ran it and tests passed; search and filter. A run shows live progress in words ("Executing step 3 of 10…"), then each test's steps with screenshots, expected and observed values, video, documents and details. Technical detail stays folded away until asked for. |
| **Tests** | Functional team, testers | Every test with its module and last result; search, filter by module or result, and choose extra columns (process, job role, owner, release validated, environment, last run, duration, tags, updated). A test's own page reads its steps in plain words with the real test data. |
| **Release impact** | Release managers, test leads | Import an Oracle update's feature list (the Readiness feature-listing spreadsheet, any .xlsx or .csv with a Feature column, or a release .json/.yaml). See which tests the update puts at risk and why, which features no test covers yet, and a suggested run under an optional time limit (critical tests always included). Tick opt-ins you have switched on, choose tests, and run just those. |
| **Tests: Manual scenarios** | Functional team, test leads | Import Excel test scripts (a Test Scenarios and Test Cases workbook, or an action list with reference numbers), or type a new scenario's steps with **New scenario** (paste several lines to get one step per line). Each scenario is listed with its cases, steps, its Quartermaster result and missing test data. **Run by hand** the first time: a signed-in browser opens, the tester marks each step Pass or Fail, Quartermaster takes a picture at each mark and makes the Word evidence document, and remembers the clicks. After that, **Run** plays the scenario by itself. Or **Prepare**: an AI follows the written steps in the pod by itself (it stops rather than guess, and never presses Save, Submit or Delete unless the step says so); a person checks its pictures and approves it before it runs. **Prepare all** does this for every scenario that needs it, one after another; **To review** then shows each scenario with the picture of every step, to tick the right ones and **Approve selected**. Scenarios are matched to release features: Release impact shows which to run and which features only a manual script covers. |
| **Needs attention** | Test team | Failures grouped by kind (checks that did not match, items not found, screens that did not respond, sign-in problems, runs that could not start, unreadable files) with the failed step, expected and observed, the screenshot and the last release it passed on. Oracle screen changes are accepted with one click (the old file is kept). Each failure says its likely cause from the run history (the Oracle update, changed data, or the test itself); when it is the update, **Draft SR** writes an Oracle service request to copy into My Oracle Support. |
| **Schedules** | Test leads | Tests that run by themselves on chosen days at a chosen time (for example every night at 02:00), while `qm serve` runs. Each shows when it runs next and links to its last run; **Run now** starts it at once. |
| **Record a test** | Functional team | Name the test and start. A browser opens already signed in. While recording: a timer, the steps so far, Pause and Resume, Add check, Add note (what should happen at a step), Mask value, Undo and Finish. |
| **Settings** | Everyone | **Clients and environments**: add each client and its pods (address, Oracle release, kind, sign-in), with test users and personas; passwords are typed here and saved encrypted (by Windows for your Windows user), never shown again. Production pods are refused. Switch the pod in use from the menu. Each client is kept apart: its own tests, manual scripts, evidence, runs, schedules, Needs attention and audit log (the first client keeps the default folders; others are in `clients/<name>-<code>/`), and every client's schedules run even when another is in use. **Backup and restore** (General tab): download one zip with your tests, run history, clients and settings, and put it back later. Also: the AI assistant (any provider; the key is kept in memory or in an environment variable), evidence options, folders, theme and keyboard shortcuts. For pods behind single sign-on or MFA, **Sign in by hand** opens a browser to sign in once; runs then reuse that session (kept in memory only). |
| **Audit log** | Test leads, auditors | Who changed what in Quartermaster and when: runs started, approvals, accepted screen changes, test data saved, imports, schedules, settings and sign-ins. Never passwords, keys or test data values. Search, and download as CSV. |

Start a run from anywhere with **New run** (or press `N`). `Ctrl+K` searches and runs anything: pages, tests,
modules, recent runs, evidence and commands such as "Open the latest failed run". The sidebar collapses to icons
(it starts collapsed on smaller screens), and the pod control at its foot shows the environment, its release and
whether the pod answered the last check.

**Masked values.** Press Mask value straight after typing something private while recording. From then on the
value is hidden in the step list, and it is never written to the test file, the run record or the evidence
documents: the test reads it from an environment variable that the recorder names when it saves (for example
`QM_HCM_VIEW_WORKER_1`); set it like the password before running. (Sign-in and password fields are never
recorded at all.)
From a terminal, `qm record` takes the same commands typed and followed by Enter: `pause`, `resume`, `check`,
`undo`, `note <text>`, `mask`, and an empty line to finish.

The pages use the Inter font when the computer can reach Google Fonts, and the system font otherwise.

Release feature lists are read from `examples/releases` (change it with `qm serve --releases <folder>`); imported
lists are kept in `.qm/releases`, and imported manual scripts in `.qm/manual` (the workbooks themselves are not kept). From a terminal, `qm run <folder> --only id1,id2` runs just those tests of a folder.

Run history is kept in `.qm/` (next to where you started `qm serve`); evidence stays in `evidence/`
as with `qm run`. The web UI needs nothing extra installed. It only answers on this computer
(127.0.0.1), and refuses requests from other web sites, so other people and pages cannot start runs.

## Backup and restore

Settings, General, **Backup and restore** (or `qm backup my-backup.zip` in a terminal) makes one zip with
everything that cannot be made again: your tests (and every client's), run history, imported manual
scripts and feature lists, schedules, the audit log, settings, and the clients and their pods.

- **Never in the zip:** the test users' passwords, the key that protects them, the AI key and the
  sign-ins done by hand. The zip is safe to keep in a shared folder. After a restore on another
  computer, type the test users' passwords again; on the same computer they are kept.
- **Evidence** (screenshots, videos, Word documents) is left out unless you tick *Also include
  evidence*, because it can be large. A backup over 2 GB is refused: copy the `evidence` folder yourself.
- **Restoring** replaces your tests, history, clients and settings with the backup. The Settings page
  stores the zip and applies it the next time Quartermaster starts (its databases are open while it
  runs). Before anything is replaced, the current state is saved in `.qm/backups/` (the last 5 are
  kept), so a restore can be undone. In a terminal, with Quartermaster closed: `qm restore my-backup.zip`.
- Evidence you already have is never deleted by a restore that does not contain evidence.

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

Running a folder of tests also writes one record for the whole run, and with `--evidence-doc`
a summary document for sign-off: overall result, every test with its result and step count, each
failure with the failing step, error and screenshot, locator changes to review, and where each
test's own document is.

```
evidence/_suites/<suite id>/
  suite.json                          every test's result and evidence location
  suite_<suite id>_summary.docx       with --evidence-doc
```

Rebuild a document at any time from a saved run folder or suite folder:
`qm document evidence/<test id>/<run id>` or `qm document evidence/_suites/<suite id>`.

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
