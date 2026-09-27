"""The browser driver's screenshot handling, with a stand-in page (no browser needed)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from quartermaster.runner.playwright_driver import PlaywrightDriver


class SlowPage:
    """Fails the first `failures` screenshots, as a page still being built does."""

    def __init__(self, failures: int):
        self.failures = failures
        self.shots = 0
        self.scripts: list[str] = []

    def screenshot(self, path: str, timeout: int) -> None:
        self.shots += 1
        if self.shots <= self.failures:
            raise TimeoutError(f"Page.screenshot: Timeout {timeout}ms exceeded.")
        Path(path).write_bytes(b"png")

    def evaluate(self, script: str, *args: Any) -> None:
        self.scripts.append(script)

    def wait_for_timeout(self, ms: int) -> None:
        pass


def driver(tmp_path: Path, page: SlowPage) -> PlaywrightDriver:
    d = PlaywrightDriver(evidence_dir=str(tmp_path), settle_ms=100)
    d.page = page
    return d


def test_a_slow_screenshot_is_tried_again_after_the_page_settles(tmp_path: Path) -> None:
    page = SlowPage(failures=1)
    path = driver(tmp_path, page).screenshot("step-04")
    assert path is not None and Path(path).read_bytes() == b"png"
    assert page.shots == 2
    assert any("__qm_highlight" in s for s in page.scripts)  # the red box is still cleared


def test_a_screenshot_that_fails_twice_is_reported(tmp_path: Path) -> None:
    page = SlowPage(failures=2)
    with pytest.raises(TimeoutError):
        driver(tmp_path, page).screenshot("step-04")
    assert page.shots == 2
    assert any("__qm_highlight" in s for s in page.scripts)
