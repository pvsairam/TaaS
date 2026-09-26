# Quartermaster (working title) — TaaS

AI-assisted regression testing that certifies each **Oracle Fusion Cloud quarterly update**
(A/B/C/D releases) before it reaches production.

> Core idea: **deterministic core, AI at the edges.** Tests are replayable YAML specs run by a
> Playwright/REST engine. AI ranks release impact, drafts tests, proposes locator heals and
> triages failures. Every AI output is validated and reviewable.

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
| `qm` CLI (`validate`, `plan`) | `src/quartermaster/cli.py` |

## Quick start

```bash
pip install -e ".[dev]"          # add ,ai for Claude, ,browser for Playwright
pytest -q

qm validate examples/tests
qm plan --release examples/releases/26D_sample.json --tests examples/tests --budget 12 --explain
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

See `examples/tests/` for complete specs.
