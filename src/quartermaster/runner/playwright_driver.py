"""Playwright driver for Oracle Fusion Cloud (Phase 1 work in progress).

Implemented: session open/close, strategy → Playwright locator mapping, basic actions,
screenshots, navigator-path navigation. Pending (see docs/PLAN.md §11 Phase 1): SSO/MFA
flows, ADF partial-page-render waits, ESS job polling via REST, REST calls with auth.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from quartermaster.domain.models import Environment, LocatorStrategy
from quartermaster.runner.credentials import persona_credentials


class PlaywrightDriver:
    """One browser per run; one fresh browser context (clean cookies) per persona login."""

    def __init__(
        self,
        *,
        headless: bool = True,
        evidence_dir: str = "evidence",
        environ: Mapping[str, str] | None = None,
        context_hook: Callable[[Any], None] | None = None,
        settle_ms: int = 15_000,
    ):
        self._headless = headless
        self._evidence = Path(evidence_dir)
        self._environ = environ
        self._context_hook = context_hook  # e.g. proxy/route setup, applied to every persona context
        self._settle_ms = settle_ms  # max wait for an element to appear, or for the network to go quiet
        # Optional pinned browser binary (e.g. a preinstalled Chromium in CI containers).
        self._executable = (os.environ if environ is None else environ).get("QM_CHROMIUM_PATH")
        self._url = ""
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self.page: Any = None
        self._inflight: set[Any] = set()

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
        if self._context_hook is not None:
            self._context_hook(self._context)
        self.page = self._context.new_page()
        self._track_requests(self.page)
        self.page.goto(self._url, wait_until="domcontentloaded")
        # Two sign-in pages exist: the classic Fusion one ("User ID" / "Sign In") and the
        # OCI IAM (IDCS) one ("Username" / "Next"). Federated SSO (Azure AD, Okta) will plug in here.
        p = self.page
        user_box = p.get_by_label("User ID", exact=True).or_(p.get_by_label("Username", exact=True))
        user_box.wait_for()
        user_box.fill(user)
        p.get_by_label("Password", exact=True).fill(password)
        sign_in = p.get_by_role("button", name="Sign In", exact=True)
        sign_in.or_(p.get_by_role("button", name="Next", exact=True)).click()
        # IDCS posts back to the pod through redirects; wait until we are on the pod again.
        pod_host = urlparse(self._url).hostname
        p.wait_for_url(lambda u: urlparse(u).hostname == pod_host, timeout=120_000)
        self._settle()

    def _track_requests(self, page: Any) -> None:
        self._inflight = set()
        page.on("request", lambda r: self._inflight.add(r) if r.url.startswith("http") else None)
        page.on("requestfinished", self._inflight.discard)
        page.on("requestfailed", self._inflight.discard)

    def _settle(self, quiet_ms: int = 500) -> None:
        """Wait until no http(s) request has been in flight for `quiet_ms`, up to the settle time.

        Playwright's "networkidle" never fires on Redwood pages: they start blob: requests
        (web workers) that never finish. Those are ignored here, and a page that stays busy
        (e.g. long polling) just costs the settle time instead of failing the step.
        """
        deadline = time.monotonic() + self._settle_ms / 1000
        quiet_since: float | None = None
        while time.monotonic() < deadline:
            if self._inflight:
                quiet_since = None
            else:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= quiet_ms / 1000:
                    return
            self.page.wait_for_timeout(100)  # also lets Playwright deliver the request events

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
        loc = self._locator(strategy, value)
        # ADF pages render after the load event (partial page rendering), so give the element a
        # moment to appear before counting. Zero matches still falls through to the next strategy.
        with suppress(Exception):  # playwright TimeoutError; the count below reports the 0
            loc.first.wait_for(state="attached", timeout=self._settle_ms)
        return int(loc.count())

    # ------------------------------------------------------------------ actions

    def navigate(self, path: str) -> None:
        """Open a page via the Navigator, e.g. 'Payables > Invoices'."""
        # Classic pages show the Navigator as the ☰ icon with a "Navigator" title.
        p = self.page
        p.get_by_role("link", name="Navigator", exact=True).first.click()
        with suppress(Exception):  # playwright TimeoutError: no grouped Navigator on this page
            p.locator("div.navmenu-header").first.wait_for(timeout=self._settle_ms)
        parts = [part.strip() for part in path.split(">")]
        for part, child in zip(parts, parts[1:], strict=False):
            # Groups are headers that expand in place, and the Navigator remembers which are
            # open. Home-page springboard links with the same names sit underneath the panel.
            child_link = p.get_by_role("link", name=child, exact=True).locator("visible=true")
            header = p.locator(f"div.navmenu-header[title='{part}']")
            if header.count() == 1:
                if child_link.count() == 0:
                    header.click()
            else:
                p.get_by_role("link", name=part, exact=True).locator("visible=true").first.click()
        p.get_by_role("link", name=parts[-1], exact=True).locator("visible=true").first.click()
        self._settle()

    def click(self, strategy: LocatorStrategy, value: str) -> None:
        self._locator(strategy, value).click()
        self._settle()

    def fill(self, strategy: LocatorStrategy, value: str, text: str) -> None:
        loc = self._locator(strategy, value)
        if loc.get_attribute("role") == "group" and loc.get_by_role("spinbutton").count():
            # Redwood date fields are month/day/year spinbuttons: typing digits from the first
            # one fills each part in turn, so "01/01/1951" is typed as 01011951.
            loc.get_by_role("spinbutton").first.focus()
            self.page.keyboard.type(re.sub(r"\D", "", text), delay=50)
            self.page.keyboard.press("Tab")
        else:
            loc.fill(text)
        self._settle()

    def select(self, strategy: LocatorStrategy, value: str, option: str) -> None:
        loc = self._locator(strategy, value)
        if loc.evaluate("el => el.tagName.toLowerCase()") == "select":
            loc.select_option(label=option)
        else:
            # ADF/Redwood choice lists are inputs with a dropdown. Redwood only searches on real
            # key presses, so type the value, then click the first suggestion containing it.
            loc.click()
            loc.fill("")
            loc.press_sequentially(option, delay=100)
            self._settle()
            suggestion = self.page.get_by_role("option").filter(has_text=option).locator("visible=true").first
            try:
                suggestion.wait_for(timeout=self._settle_ms)
                suggestion.click()
            except Exception:  # playwright TimeoutError: no suggestion list, e.g. a plain ADF choice
                loc.press("Enter")
        self._settle()

    def text_of(self, strategy: LocatorStrategy, value: str) -> str:
        loc = self._locator(strategy, value)
        if loc.evaluate("el => ['input', 'textarea'].includes(el.tagName.toLowerCase())"):
            return str(loc.input_value())  # e.g. a field filled in automatically
        return str(loc.inner_text())

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
