"""Suggest a fix for a step whose item was not found on the screen.

When every way a test knows to find something fails (Oracle renamed a button, say), the step fails
as before. Afterwards, while the page is still open, two things are tried to find what it might
have become:

1. a name on the page that looks very like the old one ("Search by Name" for "Search: Name"): no
   AI, nothing leaves this computer;
2. only when an AI is set up in Settings: the AI is shown the step and the names of the buttons,
   links and fields on the screen (personal details masked, like in Prepare) and picks one, or says
   there is none.

Either way the result is only a *suggestion*: the step still fails, nothing is changed in the test,
and the choice is checked here (it must be found exactly once on the page, by the same code that
replays tests, and must not be a Save, Delete or similar button the step never mentions). A person
accepts or ignores it in Needs attention.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

from quartermaster.ai.providers import AIError, parse_json
from quartermaster.domain.models import HealingProposal, LocatorStrategy, Step

Ask = Callable[[str, str], str]
SIMILAR_MIN = 0.75  # how alike two names must be (0 to 1) to be suggested without an AI
AI_CONFIDENCE_MAX = 0.8  # an AI is never sure enough to say more than this
_FIELDS = {"textbox", "combobox", "searchbox", "checkbox", "radio"}

SYSTEM = """You help repair a regression test for Oracle Fusion Cloud. A test step could not find its \
button, link or field because the screen changed (Oracle updates the product every quarter). You are \
shown the step and a numbered list of what is on the screen now. Choose the ONE element that is almost \
certainly the same thing under a new name or place. If you are not sure, or the step's item is simply \
not on this screen, choose none: a wrong suggestion is worse than none.
Answer with JSON only: {"element": <number or null>, "confidence": <0 to 1>, "why": "<one short sentence>"}"""


def make_healer(ask: Ask | None) -> Callable[[int, Step, Any], HealingProposal | None]:
    """The function the engine calls for a step whose item was not found. `ask` is None without an AI."""

    def healer(index: int, step: Step, driver: Any) -> HealingProposal | None:
        return suggest(index, step, driver, ask)

    return healer


def suggest(index: int, step: Step, driver: Any, ask: Ask | None) -> HealingProposal | None:
    page = getattr(driver, "page", None)
    if step.target is None or page is None:
        return None
    from quartermaster.recorder.autopilot import SNAPSHOT_JS

    screen = page.evaluate(SNAPSHOT_JS)
    items = [it for it in (screen.get("items") if isinstance(screen, dict) else None) or [] if _usable(it)]
    if not items:
        return None
    old = step.target.ordered()[0]
    written = _names(step)
    pool = _compatible(step, items)

    found = _similar(written, pool)
    if found is not None:
        item, score = found
        way = _unique_way(driver, item)
        if way is not None and not _risky(item, step):
            return _proposal(
                index, step, old, way, round(score * 0.9, 2), "similar", f'"{item["name"]}" looks like the old name'
            )
    if ask is None:
        return None
    return _ask_ai(index, step, old, driver, pool, written, ask)


# ------------------------------------------------------------------ the AI


def _ask_ai(
    index: int,
    step: Step,
    old: tuple[LocatorStrategy, str],
    driver: Any,
    pool: list[dict[str, str]],
    written: list[str],
    ask: Ask,
) -> HealingProposal | None:
    prompt = "\n".join(
        [
            f"Step: {step.intent}",
            f"What should happen: {step.expected or 'not written'}",
            "It looked for: " + (" | ".join(written) or "(a technical address)"),
            "",
            "On the screen now:",
            *(f'[{n}] {it["role"]} "{it["name"]}"' for n, it in enumerate(pool, 1)),
        ]
    )
    try:
        answer = parse_json(ask(SYSTEM, prompt))
    except AIError:
        return None  # no answer is not a problem: the step has already failed on its own
    if not isinstance(answer, dict):
        return None
    number = answer.get("element")
    if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(pool):
        return None
    item = pool[number - 1]
    way = _unique_way(driver, item)
    if way is None or _risky(item, step):
        return None
    try:
        confidence = min(float(answer.get("confidence", 0.5)), AI_CONFIDENCE_MAX)
    except (TypeError, ValueError):
        confidence = 0.5
    why = " ".join(str(answer.get("why") or "").split())[:200]
    return _proposal(index, step, old, way, max(0.0, round(confidence, 2)), "ai", why or "chosen by the AI")


# ------------------------------------------------------------------ checks


def _proposal(
    index: int,
    step: Step,
    old: tuple[LocatorStrategy, str],
    way: tuple[LocatorStrategy, str],
    confidence: float,
    source: str,
    why: str,
) -> HealingProposal:
    return HealingProposal(
        step_index=index, intent=step.intent, old=old, new=way, confidence=confidence, source=source, why=why
    )


def _usable(item: Any) -> bool:
    return isinstance(item, dict) and bool(item.get("name")) and bool(item.get("role"))


def _names(step: Step) -> list[str]:
    """The names the step looked for (its labels, link names and texts; not technical addresses)."""
    out: list[str] = []
    for kind, value in step.target.ordered() if step.target else []:
        if kind is LocatorStrategy.ROLE:
            out.append(value.partition(":")[2].strip() or value)
        elif kind in (LocatorStrategy.LABEL, LocatorStrategy.TEXT):
            out.append(value)
    return [n for n in dict.fromkeys(out) if n.strip()]


def _compatible(step: Step, items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Fields for a step that types, anything else for a step that clicks or checks."""
    from quartermaster.domain.models import Action

    if step.action in (Action.FILL, Action.SELECT):
        return [it for it in items if it["role"] in _FIELDS] or items
    return items


def _similar(written: list[str], pool: list[dict[str, str]]) -> tuple[dict[str, str], float] | None:
    """The one name on the page that is clearly the most like what the step looked for."""
    scored: list[tuple[float, dict[str, str]]] = []
    for item in pool:
        score = max((_like(w, item["name"]) for w in written), default=0.0)
        if score >= SIMILAR_MIN:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        return None  # two names are equally alike: not a safe guess
    return scored[0][1], scored[0][0]


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


def _like(a: str, b: str) -> float:
    """How alike two names are, from 0 to 1, ignoring case and punctuation."""
    return SequenceMatcher(None, _plain(a), _plain(b)).ratio()


def _unique_way(driver: Any, item: dict[str, str]) -> tuple[LocatorStrategy, str] | None:
    """A way to find this element again that finds exactly one thing on the page, as replays do."""
    role, name = item["role"], item["name"]
    full = item.get("full") or name
    ways: list[tuple[LocatorStrategy, str]] = []
    if role in _FIELDS:
        ways.append((LocatorStrategy.LABEL, name))
    if role not in ("text", "heading"):
        for n in dict.fromkeys([full, name]):
            ways.append((LocatorStrategy.ROLE, f"{role}:{n}"))
    for n in dict.fromkeys([name, item.get("title") or name]):
        ways.append((LocatorStrategy.TEXT, n))
    for strategy, value in ways:
        try:
            if driver.count(strategy, value) == 1:
                return strategy, value
        except Exception:  # a way the page cannot use is just not this one
            continue
    return None


def _risky(item: dict[str, str], step: Step) -> bool:
    """A button that changes data (Save, Delete...) is never suggested unless the step already speaks of it."""
    from quartermaster.recorder.autopilot import _RISKY

    word = _RISKY.search(item["name"])
    if word is None:
        return False
    text = f"{step.intent} {step.expected} " + " ".join(_names(step))
    return word.group(1).lower() not in text.lower()
