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
already done for this step, and what is on the screen (headings, and a numbered list of things that can be \
clicked or filled).

Answer with one JSON object and nothing else:
{"do": "click" | "fill" | "select" | "done" | "stuck", "element": <number from the list>, \
"value": "<text to type or option to choose>", "why": "<a few words>"}

- "done": the step is already complete on this screen (for example "Login" when signed in, or the page \
the step asks for is open).
- "stuck": the step needs a value the script does not give (blank, or written as <>), needs another \
person, or nothing on the screen fits.
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
    ):
        self.page, self.guide, self.recorder, self.ask = page, guide, recorder, ask
        self.settle, self.should_stop = settle, should_stop
        self.reason = ""  # why it stopped early, for the tester

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
            try:
                reply = parse_json(self.ask(SYSTEM, self._prompt(number, total, step, done, screen)))
            except AIError as e:
                return self._stuck(number, str(e))
            what = str(reply.get("do", "")).lower()
            why = " ".join(str(reply.get("why", "")).split())[:200]
            if what == "done":
                return True
            if what not in ("click", "fill", "select"):
                return self._stuck(number, why or "the AI could not see how to do it")
            item = self._item(screen, reply.get("element"))
            if item is None:
                return self._stuck(number, "the AI chose something that is not on the screen")
            value = " ".join(str(reply.get("value") or "").split())
            refusal = self._refuse(what, item, value, step)
            if refusal:
                return self._stuck(number, refusal)
            self._say(f'Step {number}: {what} {item["role"]} "{item["name"]}"{f" ({why})" if why else ""}')
            try:
                self._act(what, item, value)
            except Exception as e:  # the element went away or did not respond
                return self._stuck(number, f'{what} on "{item["name"]}" did not work: {str(e).splitlines()[0][:120]}')
            self.settle()
            done.append(f'{what} {item["role"]} "{item["name"]}"' + (f' = "{value}"' if value else ""))
        return self._stuck(number, f"not finished after {MAX_ACTIONS} actions")

    def _stuck(self, number: int, why: str) -> bool:
        self.reason = f"Step {number}: {why}"
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

    def _say(self, message: str) -> None:
        self.recorder.message = message
        self.recorder.write_feed()

    # ------------------------------------------------------------------ doing it, and remembering it

    def _locate(self, item: dict[str, str]) -> tuple[Any, list[dict[str, str]]]:
        """The element, and how to find it again on replay (only ways that find exactly one)."""
        page, role, name = self.page, item["role"], item["name"]
        ways: list[tuple[str, str, Any]] = []
        if role in ("textbox", "combobox", "searchbox"):
            ways.append(("label", name, page.get_by_label(name, exact=True)))
        if role in _ROLES:
            ways.append(("role", f"{role}:{name}", page.get_by_role(role, name=name, exact=True)))
        ways.append(("text", name, page.get_by_text(name, exact=True)))
        unique = [(s, v, loc) for s, v, loc in ways if _count(loc) == 1]
        usable = unique or [(s, v, loc) for s, v, loc in ways if _count(loc) > 1]
        if not usable:
            raise LookupError(f'"{name}" is no longer on the screen')
        candidates = [{"strategy": s, "value": v} for s, v, _ in (unique or usable)]
        return usable[0][2].first, candidates

    def _act(self, what: str, item: dict[str, str], value: str) -> None:
        element, candidates = self._locate(item)
        if what == "click":
            element.click(timeout=15000)
        elif what == "fill":
            element.fill(value, timeout=15000)
        else:
            element.select_option(label=value, timeout=15000)
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


def _count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:
        return 0
