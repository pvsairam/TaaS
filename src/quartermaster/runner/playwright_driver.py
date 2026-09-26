"""Playwright driver for Oracle Fusion Cloud (Phase 1 work in progress).

Implemented: session open/close, strategy → Playwright locator mapping, basic actions,
screenshots, navigator-path navigation. Pending (see docs/PLAN.md §11 Phase 1): SSO/MFA
flows, ADF partial-page-render waits, ESS job polling via REST, REST calls with auth.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quartermaster.domain.models import Environment, LocatorStrategy
from quartermaster.runner.credentials import persona_credentials


class PlaywrightDriver:
    """One browser per run; one fresh browser context (clean cookies) per persona login."""

    def __init__(
        self, *, headless: bool = True, evidence_dir: str = "evidence", environ: Mapping[str, str] | None = None
    ):
        self._headless = headless
        self._evidence = Path(evidence_dir)
        self._environ = environ
        # Optional pinned browser binary (e.g. a preinstalled Chromium in CI containers).
        self._executable = (os.environ if environ is None else environ).get("QM_CHROMIUM_PATH")
        self._url = ""
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self.page: Any = None

    # ------------------------------------------------------------------ lifecycle

    def open(self, env: Environment, persona: str) -> None:
        from playwright.sync_api import sync_playwright  # optional dependency

        self._url = env.url
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless, executable_path=self._executable)
        self.login_as(persona)

    def login_as(self, persona: str) -> None:
        user, password = persona_credentials(persona, self._environ)
        if self._context is not None:
            self._context.close()
        self._context = self._browser.new_context(viewport={"width": 1600, "height": 1000})
        self.page = self._context.new_page()
        self.page.goto(self._url, wait_until="domcontentloaded")
        # Native Fusion sign-in page. SSO (IDCS/OCI IAM, Azure AD, Okta) will plug in here.
        self.page.get_by_label("User ID").fill(user)
        self.page.get_by_label("Password").fill(password)
        self.page.get_by_role("button", name="Sign In").click()
        self.page.wait_for_load_state("networkidle")

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()
        self._browser = self._pw = self._context = self.page = None

    # ------------------------------------------------------------------ locators

    def _locator(self, strategy: LocatorStrategy, value: str) -> Any:
        p = self.page
        if strategy is LocatorStrategy.LABEL:
            return p.get_by_label(value, exact=True)
        if strategy is LocatorStrategy.ROLE:
            # "button:Submit" -> get_by_role("button", name="Submit")
            role, _, name = value.partition(":")
            return p.get_by_role(role.strip(), name=name.strip() or None, exact=bool(name))
        if strategy is LocatorStrategy.TEST_ID:
            return p.get_by_test_id(value)
        if strategy is LocatorStrategy.TEXT:
            return p.get_by_text(value, exact=True)
        if strategy is LocatorStrategy.CSS:
            return p.locator(value)
        if strategy is LocatorStrategy.XPATH:
            return p.locator(f"xpath={value}")
        raise ValueError(f"unsupported strategy {strategy}")

    def count(self, strategy: LocatorStrategy, value: str) -> int:
        return int(self._locator(strategy, value).count())

    # ------------------------------------------------------------------ actions

    def navigate(self, path: str) -> None:
        """Open a page via the Navigator, e.g. 'Payables > Invoices'."""
        self.page.get_by_role("link", name="Navigator").click()
        for part in (p.strip() for p in path.split(">")):
            self.page.get_by_role("link", name=part, exact=True).first.click()
        self.page.wait_for_load_state("networkidle")

    def click(self, strategy: LocatorStrategy, value: str) -> None:
        self._locator(strategy, value).click()

    def fill(self, strategy: LocatorStrategy, value: str, text: str) -> None:
        self._locator(strategy, value).fill(text)

    def select(self, strategy: LocatorStrategy, value: str, option: str) -> None:
        # ADF choice lists are not native <select>s; type-ahead + Enter works for both UIs.
        loc = self._locator(strategy, value)
        loc.fill(option)
        loc.press("Enter")

    def text_of(self, strategy: LocatorStrategy, value: str) -> str:
        return str(self._locator(strategy, value).inner_text())

    def wait_job(self, job_name: str, timeout_s: float) -> str:
        raise NotImplementedError("ESS job polling lands in Phase 1")

    def api_call(self, request: str, options: dict[str, Any]) -> int:
        raise NotImplementedError("REST steps land in Phase 1")

    def screenshot(self, name: str) -> str | None:
        if self.page is None:
            return None
        self._evidence.mkdir(parents=True, exist_ok=True)
        path = self._evidence / f"{name}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return str(path)
