"""Quartermaster's own web pages, driven in a real browser: every page opens without errors, and the main
things a person does on them work (read the lists, accept a change, import a feature list, turn on sign-in,
sign in with Google).

The sample data is built by `ui_site.py`. Skipped when Playwright is not installed."""

from __future__ import annotations

import os
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from conftest import EXAMPLES  # noqa: E402
from playwright.sync_api import Browser, Page, expect, sync_playwright  # noqa: E402
from ui_site import CLIENT, SECRET, Site, build_site, serve  # noqa: E402

WAIT = 15_000  # ms to wait for a page to show something


def chromium() -> str | None:
    return os.environ.get("QM_CHROMIUM_PATH") or (
        "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None
    )


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    pw = sync_playwright().start()
    b = pw.chromium.launch(executable_path=chromium())
    yield b
    b.close()
    pw.stop()


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Site]:
    with serve(build_site(tmp_path_factory.mktemp("ui"))) as s:
        yield s


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    """A fresh browser window. At the end it is an error if a page script failed or the console showed an error."""
    context = browser.new_context(viewport={"width": 1300, "height": 1000})
    p = context.new_page()
    p.set_default_timeout(WAIT)
    problems: list[str] = []
    p.on("pageerror", lambda e: problems.append(f"script error: {e}"))
    p.on(
        "console",
        lambda m: (
            problems.append(f"console: {m.text}")
            if m.type == "error" and "Failed to load resource" not in m.text
            else None
        ),
    )
    p.on("dialog", lambda d: d.accept())
    yield p
    context.close()
    assert problems == []


def see(page: Page, text: str | re.Pattern[str]) -> None:
    expect(page.locator("main")).to_contain_text(text, timeout=WAIT)


# ------------------------------------------------------------------ every page opens

PAGES = [
    ("#/", "Overview"),
    ("#/runs", "Runs"),
    ("#/tests", "Tests"),
    ("#/library", "Shared steps"),
    ("#/impact", "Release impact"),
    ("#/attention", "Needs attention"),
    ("#/schedules", "Schedules"),
    ("#/record", "Record a test"),
    ("#/audit", "Audit log"),
    ("#/settings?tab=general", "Settings"),
    ("#/settings?tab=evidence", "Settings"),
    ("#/settings?tab=notifications", "Settings"),
    ("#/settings?tab=users", "Settings"),
]


@pytest.mark.parametrize(("route", "heading"), PAGES)
def test_every_page_opens_and_says_what_it_is(site: Site, page: Page, route: str, heading: str) -> None:
    page.goto(f"{site.url}/{route}")
    expect(page.locator("main h1").first).to_have_text(heading, timeout=WAIT)
    expect(page.locator("main")).not_to_contain_text("Something went wrong")


def test_the_menu_takes_you_to_each_page(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/")
    for label, heading in (
        ("Runs", "Runs"),
        ("Tests", "Tests"),
        ("Shared steps", "Shared steps"),
        ("Needs attention", "Needs attention"),
    ):
        page.locator("#nav").get_by_role("link", name=re.compile(label)).first.click()
        expect(page.locator("main h1").first).to_have_text(heading, timeout=WAIT)


# ------------------------------------------------------------------ the lists


def test_the_tests_page_lists_the_tests_and_a_test_shows_its_steps(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/tests")
    see(page, "A test with shared steps")
    see(page, "View a worker")
    page.goto(f"{site.url}/#/tests/hcm%2Fshared_user.yaml")
    see(page, "Open Locations")
    expect(page.locator("main")).to_contain_text("shared: open-locations")


def test_tests_can_be_exported_as_plain_playwright_files(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/tests")
    link = page.get_by_role("link", name="Export", exact=True)
    expect(link).to_be_visible(timeout=WAIT)
    with page.expect_download() as everything:
        link.click()
    assert everything.value.suggested_filename.endswith("-playwright.zip")
    page.goto(f"{site.url}/#/tests/hcm%2Fshared_user.yaml")
    with page.expect_download() as one:
        page.get_by_role("link", name="Export", exact=True).click()
    assert one.value.suggested_filename == "hcm.shared-user-playwright.zip"
    with zipfile.ZipFile(one.value.path()) as z:
        assert {"test_hcm_shared_user.py", "fusion_runtime.py", "conftest.py"} <= set(z.namelist())
        assert "fusion.navigate('Workforce Structures > Locations')" in z.read("test_hcm_shared_user.py").decode()


def test_the_shared_steps_page_shows_the_group_and_who_uses_it(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/library")
    see(page, "Open the Locations page")
    see(page, "used by 1 test")
    see(page, "A test with shared steps")


def test_a_finished_run_shows_its_results(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/runs")
    page.locator("main a[href^='#/runs/']").first.click()
    see(page, "2 of 3 tests passed")
    see(page, "Title of hcm.view-worker")
    see(page, "Title of hcm.create-location")
    see(page, "Run again")


# ------------------------------------------------------------------ Needs attention


def test_needs_attention_shows_each_kind_and_dismissing_hides_only_that_one(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/attention")
    see(page, "Checks that did not match")
    see(page, "Cleanup that did not finish")
    see(page, "Oracle screen changes")
    see(page, "Records from this test may still be on the pod")
    see(page, "Redwood Shores")  # what the check expected
    cleanup = page.locator("article[aria-label^='Cleanup did not finish']")
    expect(cleanup).to_contain_text("The API answered HTTP 403.")
    cleanup.get_by_role("button", name="Dismiss").click()
    expect(page.locator("article[aria-label^='Cleanup did not finish']")).to_have_count(0, timeout=WAIT)
    expect(page.locator("article[aria-label^='Check did not match']")).to_have_count(1)
    # put it back for the other tests: a new run is the only way, so this test leaves it dismissed


def test_accepting_an_oracle_screen_change_updates_the_test_file(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/attention")
    card = page.locator("article[aria-label^='Oracle screen changed']")
    expect(card).to_have_count(1, timeout=WAIT)
    card.get_by_role("button", name="Accept update").click()
    expect(page.locator("article[aria-label^='Oracle screen changed']")).to_have_count(0, timeout=WAIT)
    text = (site.app.tests_root / "hcm" / "personal.yaml").read_text(encoding="utf-8")
    assert text.index("role:") < text.index("label:")  # the role is tried first now


# ------------------------------------------------------------------ Settings


def test_settings_remember_how_many_tests_run_at_once(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/settings?tab=evidence")
    group = page.get_by_role("radiogroup", name="Tests at the same time")
    group.get_by_role("radio", name="3").click()
    expect(page.get_by_text("Saved. Runs started from now on use it.")).to_be_visible(timeout=WAIT)
    page.reload()
    expect(
        page.get_by_role("radiogroup", name="Tests at the same time").get_by_role("radio", name="3")
    ).to_have_attribute("aria-checked", "true", timeout=WAIT)


def test_automatic_backups_can_be_made_and_their_settings_are_checked(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/settings?tab=general")
    card = page.locator("section", has_text="Automatic backups")
    expect(card).to_contain_text("once a day after 02:00", timeout=WAIT)
    card.get_by_role("button", name="Back up now").click()
    expect(page.locator("section", has_text="Automatic backups")).to_contain_text(
        re.compile(r"Saved copies \(\d+\)"), timeout=WAIT
    )
    page.fill("#ab-keep", "99")
    page.locator("section", has_text="Automatic backups").get_by_role("button", name="Save").click()
    expect(page.locator("section", has_text="Automatic backups")).to_contain_text(
        "keep between 1 and 30 backups", timeout=WAIT
    )


def test_pod_discovery_is_off_until_it_is_allowed_and_can_be_switched_off_again(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/settings?tab=environments")
    card = page.locator("section", has_text="Pod discovery")
    expect(card).to_contain_text("Nothing is read until you allow it", timeout=WAIT)
    expect(card.get_by_role("button", name="Look at the pod now")).to_be_disabled()
    page.get_by_label("Allow pod discovery for this pod").check()
    expect(page.locator("section", has_text="Pod discovery")).to_contain_text("On for this pod", timeout=WAIT)
    expect(page.get_by_role("button", name="Look at the pod now")).to_be_enabled()
    page.get_by_label("Allow pod discovery for this pod").uncheck()
    expect(page.locator("section", has_text="Pod discovery")).to_contain_text(
        "Nothing is read until you allow it", timeout=WAIT
    )


def test_the_ai_quality_check_is_there_and_needs_an_ai_to_be_chosen_first(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/settings?tab=ai")
    card = page.locator("section", has_text="AI quality check")
    expect(card).to_contain_text("Not run yet", timeout=WAIT)
    expect(card).to_contain_text("made-up questions")
    expect(card.get_by_role("button", name="Check this AI")).to_be_disabled()


# ------------------------------------------------------------------ ticket links


def test_a_ticket_can_be_written_linked_and_removed_from_a_failure(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/settings?tab=general")
    page.fill("#tt-link", "https://example.atlassian.net/browse/{key}")
    page.fill(
        "#tt-create",
        "https://example.atlassian.net/secure/CreateIssueDetails!init.jspa?summary={title}&description={description}",
    )
    page.locator("section", has_text="Ticket tracker").get_by_role("button", name="Save").click()
    expect(page.get_by_text("Saved.", exact=True)).to_be_visible(timeout=WAIT)

    page.goto(f"{site.url}/#/attention")
    card = page.locator("article[aria-label^='Check did not match']")
    card.get_by_role("button", name="Ticket", exact=True).click()
    drawer = page.locator(".drawer")
    expect(drawer.locator("textarea")).to_have_value(re.compile("Redwood Shores"), timeout=WAIT)
    expect(drawer.get_by_role("link", name=re.compile("Open .* with it|Open the tracker with it"))).to_be_visible()
    page.fill("#tk-ref", "javascript:alert(1)")
    drawer.get_by_role("button", name="Link ticket").click()
    expect(drawer).to_contain_text("a ticket number uses letters", timeout=WAIT)
    page.fill("#tk-ref", "PROJ-5")
    drawer.get_by_role("button", name="Link ticket").click()
    expect(drawer.locator("a[href='https://example.atlassian.net/browse/PROJ-5']")).to_be_visible(timeout=WAIT)
    drawer.get_by_role("button", name="Close", exact=True).last.click()
    expect(page.locator("article[aria-label^='Check did not match'] a[href$='/browse/PROJ-5']")).to_be_visible(
        timeout=WAIT
    )

    page.goto(f"{site.url}/#/tests/hcm%2Flocation.yaml")  # the failing test shows its ticket too
    expect(page.locator("main [data-tickets] a")).to_have_text("PROJ-5", timeout=WAIT)

    page.goto(f"{site.url}/#/attention")
    page.locator("article[aria-label^='Check did not match']").get_by_role(
        "button", name=re.compile(r"Ticket \(1\)")
    ).click()
    page.locator(".drawer").get_by_role("button", name="Remove").click()
    expect(page.locator(".drawer")).to_contain_text("No ticket linked yet", timeout=WAIT)


# ------------------------------------------------------------------ Release impact: What's New


def test_a_saved_whats_new_page_is_read_and_saved_as_a_feature_list(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/impact")
    page.get_by_role("button", name="Import feature list").first.click()
    page.set_input_files("input[type=file]", str(EXAMPLES / "releases" / "26D_whats_new_sample.html"))
    drawer = page.locator(".drawer")
    expect(drawer).to_contain_text("4 features found for release 26D", timeout=WAIT)
    expect(drawer).to_contain_text("Invoice Approval by Line")
    drawer.get_by_role("button", name="Save feature list").click()
    expect(page).to_have_url(re.compile(r"#/impact\?release=26D\.json"), timeout=WAIT)


def test_pasted_whats_new_text_can_be_checked(site: Site, page: Page) -> None:
    page.goto(f"{site.url}/#/impact")
    page.get_by_role("button", name="Import feature list").first.click()
    page.fill("#imp-paste", (EXAMPLES / "releases" / "26D_whats_new_sample.txt").read_text(encoding="utf-8"))
    page.locator(".drawer").get_by_role("button", name="Check file").click()
    expect(page.locator(".drawer")).to_contain_text("2 features found for release 26D", timeout=WAIT)


# ------------------------------------------------------------------ sign-in


@pytest.fixture
def secure(tmp_path: Path) -> Iterator[Site]:
    """Its own Quartermaster: turning sign-in on must not change the pages the other tests use."""
    with serve(build_site(tmp_path)) as s:
        yield s


def test_turning_on_sign_in_then_adding_and_signing_in_a_user(secure: Site, page: Page, browser: Browser) -> None:
    page.goto(f"{secure.url}/#/settings?tab=users")
    page.fill("#on-name", "Sai Ram")
    page.fill("#on-user", "sai")
    page.fill("#on-pw", "correct-horse-battery")
    page.fill("#on-again", "correct-horse-battery")
    page.get_by_role("button", name="Turn on sign-in").click()
    expect(page.locator("#nav")).to_contain_text("Sign out", timeout=WAIT)  # you are the first administrator, signed in
    page.goto(f"{secure.url}/#/settings?tab=users")
    expect(page.locator("main")).to_contain_text("1 person can sign in", timeout=WAIT)

    page.get_by_role("button", name="Add a user").click()
    page.fill("#u-name", "Jo Tester")
    page.fill("#u-user", "jo")
    page.locator(".drawer").get_by_role("button", name="Add the user").click()
    expect(page.locator(".drawer")).to_contain_text("This is the only time it is shown", timeout=WAIT)
    temporary = page.locator(".drawer div[style*='monospace']").inner_text().strip()
    assert len(temporary) >= 10
    page.locator(".drawer").get_by_role("button", name="Done").click()

    # a second browser window is a stranger: it sees only the sign-in
    other = browser.new_context()
    stranger = other.new_page()
    stranger.set_default_timeout(WAIT)
    stranger.goto(f"{secure.url}/")
    expect(stranger.locator("main")).to_contain_text("Sign in to Quartermaster", timeout=WAIT)
    stranger.fill("input[aria-label='User name']", "jo")
    stranger.fill("input[aria-label='Password']", "not-the-password")
    stranger.get_by_role("button", name="Sign in", exact=True).click()
    expect(stranger.locator("main")).to_contain_text("wrong user name or password", timeout=WAIT)
    stranger.fill("input[aria-label='Password']", temporary)
    stranger.get_by_role("button", name="Sign in", exact=True).click()
    expect(stranger.locator("main")).to_contain_text("Choose your own password", timeout=WAIT)
    other.close()


def test_continue_with_google_signs_in_only_people_the_administrator_added(
    secure: Site, page: Page, browser: Browser
) -> None:
    # sign-in on, Google set up and one Google-only user, made through the pages
    page.goto(f"{secure.url}/#/settings?tab=users")
    page.fill("#on-name", "Sai Ram")
    page.fill("#on-user", "sai")
    page.fill("#on-pw", "correct-horse-battery")
    page.fill("#on-again", "correct-horse-battery")
    page.get_by_role("button", name="Turn on sign-in").click()
    expect(page.locator("#nav")).to_contain_text("Sign out", timeout=WAIT)
    page.goto(f"{secure.url}/#/settings?tab=users")
    expect(page.locator("main")).to_contain_text("Sign in with Google", timeout=WAIT)
    page.fill("#g-id", CLIENT)
    page.fill("#g-secret", SECRET)
    page.get_by_label("Turn on Continue with Google").check()
    page.locator("section", has_text="Sign in with Google").get_by_role("button", name="Save").click()
    expect(page.locator("main")).to_contain_text("On: people can use Continue with Google", timeout=WAIT)
    expect(page.locator("main")).not_to_contain_text(SECRET)  # the secret is never shown again

    page.get_by_role("button", name="Add a user").click()
    page.fill("#u-name", "Jane Doe")
    page.fill("#u-user", "jane")
    page.fill("#u-mail", "Jane.Doe@gmail.com")
    page.locator(".drawer").get_by_role("button", name="Add the user").click()
    expect(page.locator("main")).to_contain_text("jane.doe@gmail.com", timeout=WAIT)

    # Jane, in her own window: Gmail ignores the dots, so janedoe@gmail.com is the same person
    secure.google.email = "janedoe@gmail.com"
    jane_window = browser.new_context()
    jane = jane_window.new_page()
    jane.set_default_timeout(WAIT)
    jane.goto(f"{secure.url}/")
    jane.locator("#login-google").click()
    expect(jane.locator("main h1").first).to_have_text("Overview", timeout=WAIT)
    me = jane.evaluate("fetch('/api/auth/status').then(r => r.json()).then(s => s.user.username)")
    assert me == "jane"
    jane_window.close()

    # someone nobody added is turned away with a plain sentence
    secure.google.email = "stranger@gmail.com"
    stranger_window = browser.new_context()
    stranger = stranger_window.new_page()
    stranger.set_default_timeout(WAIT)
    stranger.goto(f"{secure.url}/")
    stranger.locator("#login-google").click()
    expect(stranger.locator("[role=alert]").first).to_contain_text("has not been given access", timeout=WAIT)
    stranger_window.close()
