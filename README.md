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
| `qm` CLI (`validate`, `plan`) | `src/quartermaster/cli.py` |

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

## Connecting to a Fusion test environment

Credentials are read from environment variables and never go in specs or Git:

| Variable | Purpose |
|---|---|
| `QM_FUSION_URL` | Non-prod pod URL, e.g. `https://xxxx-test.fa.us2.oraclecloud.com` |
| `QM_FUSION_USER` / `QM_FUSION_PASSWORD` | Default test user |
| `QM_FUSION_USER_<PERSONA>` / `QM_FUSION_PASSWORD_<PERSONA>` | Per-persona user, e.g. `QM_FUSION_USER_LINE_MANAGER` |

The runner refuses production pods. Use dedicated test users, not real employees' accounts.
