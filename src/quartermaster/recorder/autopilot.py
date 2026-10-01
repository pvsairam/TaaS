"""Prepare a manual scenario automatically: an AI follows the written steps in the signed-in pod.

For each written step the AI is shown the step, what should happen, and what is on the screen:
the headings and a numbered list of the buttons, links and fields that can be used. It answers
with one action (click, fill, select), or says the step is done or that it is stuck. Quartermaster
does the action itself, so only things that are really on the screen can be used, and records it
the same way a person's click is recorded. When a step is done a picture is taken (see Guide).

The AI never decides that a test passed on its own: the result is a draft that a person reviews
(its pictures) and approves before it is run every quarter. It stops at the first step it cannot
do, never types values the script does not give, and does not press buttons that change data
(Save, Submit, Delete, Approve...) unless the step says so.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quartermaster.ai.providers import AIError, parse_json

MAX_ACTIONS = 5  # per written step
_RISKY = re.compile(
    r"\b(submit|save|delete|remove|approve|reject|withdraw|terminate|post|send|confirm|cancel|apply|sign out)\b", re.I
)
_ROLES = {
    "link",
    "button",
    "menuitem",
    "tab",
    "option",
    "treeitem",
    "checkbox",
    "radio",
    "textbox",
    "combobox",
    "searchbox",
}

SYSTEM = """You help test Oracle Fusion Cloud. A tester's written test script is being carried out in a \
browser that is already signed in. You get ONE step at a time: the step, what should happen, what was \
already done for this step (including actions that did not work), and what is on the screen (headings, and \
a numbered list of things that can be clicked or filled).

Answer with one JSON object and nothing else:
{"do": "click" | "fill" | "select" | "navigate" | "done" | "stuck", "element": <number from the list>, \
"value": "<text to type, option to choose, or Navigator path>", "why": "<a few words>"}

- "navigate": open a page from the Navigator menu by its path, for example {"do": "navigate", \
"value": "Me > Personal Information"} or "My Client Groups > Person Management". Prefer this to clicking \
through the Navigator menu yourself: menu groups are headers that expand, and their items can be hidden. \
A group name alone, for example {"do": "navigate", "value": "Me"}, opens that group and lists its pages: \
use it when a step only names a group, then answer "done" for that step.
- "click": a button, link, tab or tile from the list, by its number. Elements of kind "text" are cards or \
tiles that open something when clicked (for example "Employment Info" on Personal Info).
- "done": the step is already complete on this screen (for example "Login" when signed in, or the page \
the step asks for is open). A later step may already be done by an earlier navigate.
- "stuck": the step needs a value the script does not give (blank, or written as <>), needs another \
person, or nothing on the screen fits even after trying another way.
- If an action did not work, try a different way (for example navigate instead of click).
- Only choose elements from the list. Prefer the exact words of the step.
- Never type a value that is not written in the step.
- One action per answer."""

CHECK_SYSTEM = """You help test Oracle Fusion Cloud. A test scenario has just been carried out. Choose up \
to two texts on the screen that prove the scenario reached the right page or result, for example a page \
heading or a field label. Answer with one JSON object and nothing else: \
{"check": [<numbers from the TEXTS list>], "why": "<a few words>"}. If nothing proves it, {"check": []}."""

# What the AI is shown of the page: never values typed in fields, only labels and visible names.
SNAPSHOT_JS = r"""() => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const clean = (t) => (t || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  const roleOf = (el) => { const r = el.getAttribute('role'); if (r) return r; const t = el.tagName.toLowerCase();
    if (t === 'a') return 'link'; if (t === 'button') return 'button'; if (t === 'select') return 'combobox';
    if (t === 'textarea') return 'textbox';
    if (t === 'input') { const ty = (el.type || 'text').toLowerCase();
      if (['button', 'submit', 'reset'].includes(ty)) return 'button'; if (ty === 'checkbox') return 'checkbox';
      if (ty === 'radio') return 'radio'; return 'textbox'; }
    return t; };
  const labelOf = (el) => { if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return clean(l.innerText); }
    return clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('title')); };
  const nameOf = (el) => clean(el.getAttribute('aria-label') || el.innerText || el.getAttribute('title')
    || el.getAttribute('alt'));
  const inToolbar = (el) => el.closest('[data-qm-toolbar], #__qm_toolbar, .__qm');
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], ' +
    '[role=menuitem], [role=tab], [role=option], [role=treeitem], [onclick]';
  const items = [], seen = new Set();
  for (const el of document.querySelectorAll(sel)) {
    if (items.length >= 150) break;
    if (!vis(el) || inToolbar(el)) continue;
    const role = roleOf(el);
    const field = ['textbox', 'combobox', 'searchbox', 'checkbox', 'radio'].includes(role);
    const name = field ? labelOf(el) : nameOf(el);
    if (!name || seen.has(role + '|' + name)) continue;
    seen.add(role + '|' + name);
    items.push({role, name});
  }
  // Cards and tiles (for example Redwood's Personal Info cards) are often plain boxes that react to
  // a click: their text shows the hand cursor, but they are not links or buttons.
  const names = new Set(items.map((it) => it.name));
  for (const el of document.querySelectorAll('h1, h2, h3, h4, h5, h6, span, div, p, li, td, label')) {
    if (items.length >= 150) break;
    if (el.children.length || !vis(el) || inToolbar(el) || el.closest(sel)) continue;
    if (getComputedStyle(el).cursor !== 'pointer') continue;
    const name = clean(el.innerText);
    if (name.length < 2 || name.length > 60 || names.has(name)) continue;
    names.add(name);
    items.push({role: 'text', name});
  }
  const heads = [...document.querySelectorAll('h1, h2, h3, [role=heading]')].filter(vis)
    .map((e) => clean(e.innerText)).filter(Boolean);
  const texts = [], tseen = new Set();
  for (const el of document.querySelectorAll('h1, h2, h3, h4, [role=heading], label, th, dt, span, div, p, td')) {
    if (texts.length >= 120) break;
    if (el.children.length || !vis(el) || inToolbar(el)) continue;
    const t = clean(el.innerText);
    if (t.length < 2 || t.length > 60 || tseen.has(t)) continue;
    tseen.add(t); texts.push(t);
  }
  return {title: document.title, headings: [...new Set(heads)].slice(0, 20), items, texts};
}"""


Ask = Callable[[str, str], str]


class Autopilot:
    def __init__(
        self,
        page: Any,
        guide: Any,
        recorder: Any,
        ask: Ask,
        settle: Callable[[], None] = lambda: None,
        should_stop: Callable[[], bool] = lambda: False,
        navigate: Callable[[str], None] | None = None,
    ):
        self.page, self.guide, self.recorder, self.ask = page, guide, recorder, ask
        self.settle, self.should_stop, self.navigate = settle, should_stop, navigate
        self.reason = ""  # why it stopped early, for the tester
        # What the AI answered and what happened, step by step, kept with the run's evidence so a
        # person can see why it stopped. Only labels from the screen, never typed values or keys.
        run_dir = getattr(guide, "run_dir", None)
        self.diary = Path(run_dir) / "ai-diary.txt" if run_dir else None
        self.nav_pages: dict[str, str] = {}  # page link -> its Navigator group, once a group was opened

    # ------------------------------------------------------------------ the loop

    def run(self) -> bool:
        """Do every step. True only when all of them were done (the draft is then worth reviewing)."""
        steps = self.guide.steps
        for i, step in enumerate(steps):
            number = i + 1
            if not self._do_step(number, step, len(steps)):
                return False
            if number == len(steps):
                self._add_checks(step)
            self.guide.mark(f"{number} pass", self.page)
            self._say(f"Step {number} done.")
        self._say("Every step is done. Saving.")
        return True

    def _do_step(self, number: int, step: dict[str, str], total: int) -> bool:
        done: list[str] = []
        for _ in range(MAX_ACTIONS):
            if self.should_stop():
                return self._stuck(number, "stopped by the tester")
            screen = self._screen()
            if not done:
                self._note(f"\nStep {number}: {step['action']}")
            self._note(f"  Screen: {screen.get('title', '')} ({len(screen.get('items', []))} things to click or fill)")
            self._note(
                "  Shown: "
                + " | ".join(f"[{i}] {it['role']} {it['name']}" for i, it in enumerate(screen.get("items", []), 1))
            )
            self._say(f"Step {number}: asking the AI what to do" + (f" (try {len(done) + 1})" if done else ""))
            try:
                answer = self.ask(SYSTEM, self._prompt(number, total, step, done, screen))
                self._note(f"  AI answered: {' '.join(answer.split())[:400]}")
                reply = parse_json(answer)
            except AIError as e:
                return self._stuck(number, str(e))
            what = str(reply.get("do", "")).lower()
            why = " ".join(str(reply.get("why", "")).split())[:200]
            value = " ".join(str(reply.get("value") or "").split())
            if what == "done":
                return True
            if what == "navigate" and self.navigate is not None and value:
                self._open(number, value, why, done)
                continue
            if what not in ("click", "fill", "select"):
                return self._stuck(number, why or "the AI could not see how to do it")
            item = self._item(screen, reply.get("element"))
            if item is None:
                done.append(f"chose element {reply.get('element')!r}, which is NOT on the screen")
                continue
            group = self.nav_pages.get(item["name"]) if what == "click" and item["role"] == "link" else None
            if group and self.navigate is not None:
                # A page in an open Navigator group: replays open it the same way, from the Navigator
                self._open(number, f"{group} > {item['name']}", why, done)
                continue
            refusal = self._refuse(what, item, value, step)
            if refusal:
                return self._stuck(number, refusal)
            self._say(f'Step {number}: {what} {item["role"]} "{item["name"]}"{f" ({why})" if why else ""}')
            self._note(f'  Doing: {what} {item["role"]} "{item["name"]}"')
            action = f'{what} {item["role"]} "{item["name"]}"' + (f' = "{value}"' if value else "")
            try:
                self._act(what, item, value)
            except Exception as e:  # hidden, covered or gone: tell the AI and let it try another way
                done.append(f"{action} DID NOT WORK ({_first_line(e)})")
                self._note(f"  Did not work: {_first_line(e)}")
                self._say(f"Step {number}: that did not work. Trying another way.")
                continue
            self.settle()
            done.append(action)
        return self._stuck(number, f"not finished after {MAX_ACTIONS} actions")

    def _stuck(self, number: int, why: str) -> bool:
        self.reason = f"Step {number}: {why}"
        self._note(f"  STOPPED: {why}")
        self.guide.mark(f"{number} fail The AI could not do this step: {why}", self.page)
        self._say(f"Stopped at step {number}: {why}. Do this scenario by hand instead.")
        return False

    # ------------------------------------------------------------------ the screen and the AI

    def _screen(self) -> dict[str, Any]:
        for _ in range(3):
            try:
                screen = self.page.evaluate(SNAPSHOT_JS)
                if isinstance(screen, dict):
                    return screen
            except Exception:  # the page was navigating
                self.settle()
        return {"title": "", "headings": [], "items": [], "texts": []}

    @staticmethod
    def _prompt(number: int, total: int, step: dict[str, str], done: list[str], screen: dict[str, Any]) -> str:
        lines = [
            f"Step {number} of {total}: {step['action']}",
            f"What should happen: {step['expected'] or 'not written'}",
            f"Test case: {step.get('case_name') or step.get('case') or ''}",
            "Already done for this step: " + ("; ".join(done) if done else "nothing yet"),
            "",
            f"SCREEN: {screen.get('title', '')}",
            "Headings: " + " | ".join(screen.get("headings", [])),
            "Elements:",
            *(f'[{i}] {it["role"]} "{it["name"]}"' for i, it in enumerate(screen.get("items", []), 1)),
        ]
        return "\n".join(lines)

    @staticmethod
    def _item(screen: dict[str, Any], number: Any) -> dict[str, str] | None:
        items = screen.get("items", [])
        try:
            n = int(number)
        except (TypeError, ValueError):
            return None
        return items[n - 1] if 1 <= n <= len(items) else None

    @staticmethod
    def _refuse(what: str, item: dict[str, str], value: str, step: dict[str, str]) -> str:
        written = f"{step['action']} {step['expected']}".lower()
        word = _RISKY.search(item["name"])
        if what == "click" and word and word.group(1).lower() not in written:
            return f'it would have to click "{item["name"]}", which can change data, and the step does not say so'
        if what in ("fill", "select") and (not value or "<" in value or value.lower() not in written):
            return "the step does not give the value to enter"
        return ""

    def _open(self, number: int, value: str, why: str, done: list[str]) -> None:
        """Open a page from the Navigator ("Me > Personal Information"), or a group on its own ("Me")."""
        assert self.navigate is not None
        self._say(f"Step {number}: open {value} from the Navigator{f' ({why})' if why else ''}")
        if ">" not in value:
            try:
                group, pages = self._open_group(value)
            except Exception as e:  # not a group, or it would not open: say so, like a failed path
                group, pages = "", []
                self._note(f"  Could not open the group: {_first_line(e)}")
            if group:
                shown = ", ".join(pages) if pages else "none could be read"
                done.append(
                    f'opened the Navigator group "{group}". Its pages: {shown}. If the step only names this group,'
                    f' it is done. To open one of its pages, navigate "{group} > <page>".'
                )
                self._note(f"  Opened the Navigator group {group}; its pages: {shown}")
                return
        try:
            self.navigate(value)
        except Exception as e:  # the path is not in this Navigator: let the AI try another way
            groups = self._navigator_groups()
            done.append(
                f'navigate "{value}" DID NOT WORK ({_first_line(e)}).'
                + (f" The Navigator's groups are: {', '.join(groups)}." if groups else "")
                + ' Use the exact names shown, as "Group > Page", or the group name alone to see its pages.'
            )
            self._note(
                f"  Did not work: {_first_line(e)}" + (f"; Navigator groups: {', '.join(groups)}" if groups else "")
            )
            self._say(f"Step {number}: {value} is not in the Navigator. Trying another way.")
            return
        self.recorder.events.append({"kind": "navigate", "value": value})
        done.append(f'navigate "{value}"')

    def _links(self) -> list[str]:
        return [it["name"] for it in self._screen().get("items", []) if it.get("role") == "link"]

    def _open_group(self, name: str) -> tuple[str, list[str]]:
        """Expand one Navigator group (opening the Navigator first) and return its exact name and the
        pages it shows. ("", []) when there is no such group. Nothing is recorded: a replay opens the
        group itself when it navigates to one of its pages."""
        page = self.page
        headers = page.locator("div.navmenu-header")
        if headers.locator("visible=true").count() == 0:
            page.get_by_role("link", name="Navigator", exact=True).first.click(timeout=10_000)
            self.settle()
        group = next((g for g in self._navigator_groups() if g.lower() == name.strip().lower()), "")
        if not group:
            return "", []
        header = headers.filter(has_text=re.compile(rf"^\s*{re.escape(group)}\s*$")).locator("visible=true")
        exact = page.locator("div.navmenu-header[title=" + _css_string(group) + "]").locator("visible=true")
        if exact.count():
            header = exact
        before = self._links()
        header.first.click(timeout=10_000)
        self.settle()
        after = self._links()
        if len(after) < len(before):  # it was open already, and that click closed it: open it again
            header.first.click(timeout=10_000)
            self.settle()
            before, after = after, self._links()
        pages = [n for n in after if n not in before]
        for n in pages:
            self.nav_pages[n] = group
        return group, pages[:40]

    def _navigator_groups(self) -> list[str]:
        """The names of the Navigator's groups, so the AI can use the pod's exact words."""
        try:
            names = self.page.evaluate(
                "() => [...document.querySelectorAll('div.navmenu-header')]"
                ".map((e) => (e.getAttribute('title') || e.innerText || '').trim()).filter(Boolean)"
            )
        except Exception:
            return []
        return [str(n)[:60] for n in names][:40] if isinstance(names, list) else []

    def _note(self, line: str) -> None:
        if self.diary is None:
            return
        try:
            self.diary.parent.mkdir(parents=True, exist_ok=True)
            with self.diary.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # the diary only helps to explain; never stop the AI for it

    def _say(self, message: str) -> None:
        self.recorder.message = message
        self.recorder.write_feed()

    # ------------------------------------------------------------------ doing it, and remembering it

    def _locate(self, item: dict[str, str]) -> tuple[Any, list[dict[str, str]]]:
        """The visible element, and how to find it again on replay. Replay needs a way that finds
        exactly one element on the whole page (hidden copies too), so those ways come first."""
        page, role, name = self.page, item["role"], item["name"]
        ways: list[tuple[str, str, Any]] = []
        if role in ("textbox", "combobox", "searchbox"):
            ways.append(("label", name, page.get_by_label(name, exact=True)))
        if role in _ROLES:
            ways.append(("role", f"{role}:{name}", page.get_by_role(role, name=name, exact=True)))
        ways.append(("text", name, page.get_by_text(name, exact=True)))
        shown = [(s, v, _visible(loc)) for s, v, loc in ways]
        clickable = [(s, v, loc) for s, v, loc in shown if _count(loc) >= 1]
        if not clickable:
            raise LookupError(f'"{name}" is not shown on the screen')
        everywhere_one = [(s, v) for s, v, loc in ways if _count(loc) == 1]
        shown_one = [(s, v) for s, v, loc in shown if _count(loc) == 1]
        chosen = everywhere_one or shown_one or [(s, v) for s, v, _ in clickable]
        return clickable[0][2].first, [{"strategy": s, "value": v} for s, v in chosen]

    def _act(self, what: str, item: dict[str, str], value: str) -> None:
        element, candidates = self._locate(item)
        if what == "click":
            element.click(timeout=8000)
        elif what == "fill":
            element.fill(value, timeout=8000)
        else:
            element.select_option(label=value, timeout=8000)
        event: dict[str, Any] = {"kind": what, "intent": item["name"], "candidates": candidates}
        if what in ("fill", "select"):
            event["value"] = value
        self.recorder.events.append(event)

    def _add_checks(self, step: dict[str, str]) -> None:
        """Checks that prove the last page is the right one, so a replay cannot pass on a wrong page."""
        screen = self._screen()
        texts = screen.get("texts", [])
        if not texts:
            return
        scenario = self.guide.scenario
        fields = scenario.get("fields") or []
        prompt = "\n".join(
            [
                f"Scenario: {scenario.get('title', '')}",
                f"Last step: {step['action']}",
                f"What should happen: {step['expected'] or 'not written'}",
                "Fields the page should show: " + (", ".join(fields) if fields else "not written"),
                "TEXTS:",
                *(f"[{i}] {t}" for i, t in enumerate(texts, 1)),
            ]
        )
        try:
            chosen = parse_json(self.ask(CHECK_SYSTEM, prompt)).get("check") or []
        except AIError:
            return
        for n in chosen[:2]:
            if isinstance(n, int) and 1 <= n <= len(texts):
                text = texts[n - 1]
                if _count(self.page.get_by_text(text, exact=True)) >= 1:
                    self.recorder.events.append(
                        {"kind": "assert_visible", "intent": text, "candidates": [{"strategy": "text", "value": text}]}
                    )
        self._say(f"Added {len(chosen[:2])} check(s) that prove the page is right.")


def _visible(locator: Any) -> Any:
    try:
        return locator.locator("visible=true")
    except Exception:  # a stand-in page without visibility filtering
        return locator


def _css_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _first_line(e: Exception) -> str:
    return (str(e).splitlines() or [type(e).__name__])[0][:120]


def _count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:
        return 0
