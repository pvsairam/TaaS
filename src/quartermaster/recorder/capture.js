// Injected into every page during `qm record`. Captures user clicks and field changes and
// sends each one, with several candidate locators, to Python via window.__qmRecord.
(() => {
  if (window.__qmInstalled) return;
  window.__qmInstalled = true;

  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const short = (s) => (s && s.length <= 60 ? s : "");
  // ADF generates ids like "pt1:_FOr1:1:_FONSr2:0:..." that change between releases.
  const stableId = (id) => id && !id.includes(":") && !/\d{3,}/.test(id);

  const labelOf = (el) => {
    if (el.labels && el.labels.length) return clean(el.labels[0].innerText);
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by.split(/\s+/).map((i) => document.getElementById(i)).filter(Boolean).map((n) => n.innerText).join(" ");
      if (clean(t)) return clean(t);
    }
    return clean(el.getAttribute("aria-label")) || "";
  };

  const roleOf = (el) => {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (tag === "button" || ["submit", "button", "reset"].includes(type)) return "button";
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "select") return "combobox";
    if (tag === "textarea" || (tag === "input" && ["", "text", "search", "email", "number", "tel", "date"].includes(type))) return "textbox";
    if (type === "checkbox" || type === "radio") return type;
    return "";
  };

  const nameOf = (el) =>
    clean(el.getAttribute("aria-label")) || labelOf(el) || short(clean(el.innerText)) || clean(el.value) || clean(el.getAttribute("title"));

  const candidates = (el) => {
    const out = [];
    const add = (strategy, value) => {
      if (value && !out.some((c) => c.strategy === strategy && c.value === value)) out.push({ strategy, value });
    };
    const isField = ["input", "select", "textarea"].includes(el.tagName.toLowerCase());
    if (isField) add("label", labelOf(el));
    const role = roleOf(el);
    const name = nameOf(el);
    if (role && name) add("role", `${role}:${name}`);
    if (el.dataset && el.dataset.testid) add("test_id", el.dataset.testid);
    if (!isField) add("text", short(clean(el.innerText)));
    if (!isField && !clean(el.innerText)) add("text", clean(el.getAttribute("title")));
    if (stableId(el.id) && document.querySelectorAll(`#${CSS.escape(el.id)}`).length === 1) add("css", `#${el.id}`);
    return out;
  };

  const CLICKABLE =
    "button, a, [role=button], [role=link], [role=menuitem], [role=tab], [role=option], " +
    "input[type=submit], input[type=button], input[type=checkbox], input[type=radio]";

  const send = (payload) => {
    try {
      window.__qmRecord(payload);
    } catch (e) {
      /* binding not ready */
    }
  };

  // A text field only fires "change" when it loses focus, which can be *after* the user's
  // next action. Track typing as it happens and flush it before any other recorded event,
  // so steps are saved in the order the user performed them.
  let pending = null;
  const sentValue = new WeakMap(); // element -> last value recorded, to skip duplicate changes
  const sendField = (el) => {
    const ev = fieldEvent(el);
    if (sentValue.get(el) === ev.value) return;
    sentValue.set(el, ev.value);
    send(ev);
  };
  const fieldEvent = (el) => {
    const tag = el.tagName.toLowerCase();
    return {
      kind: tag === "select" ? "select" : "fill",
      intent: labelOf(el) || nameOf(el),
      candidates: candidates(el),
      value: tag === "select" ? clean(el.options[el.selectedIndex]?.text) : el.value,
      url: location.href,
    };
  };
  const flush = () => {
    if (pending) {
      sendField(pending);
      pending = null;
    }
  };
  const recordable = (el) => {
    const tag = (el.tagName || "").toLowerCase();
    if (!["input", "select", "textarea"].includes(tag)) return false;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (["checkbox", "radio", "submit", "button"].includes(type)) return false; // captured as clicks
    return type !== "password"; // never record secrets
  };

  document.addEventListener(
    "input",
    (e) => {
      const el = e.target;
      if (!recordable(el) || el.tagName.toLowerCase() === "select") return;
      if (pending && pending !== el) flush();
      pending = el;
    },
    true
  );

  document.addEventListener(
    "change",
    (e) => {
      const el = e.target;
      if (!recordable(el)) return;
      if (pending && pending !== el) flush();
      pending = null;
      sendField(el);
    },
    true
  );

  document.addEventListener(
    "click",
    (e) => {
      const el = e.target.closest && e.target.closest(CLICKABLE);
      if (!el) return;
      flush();
      send({ kind: "click", intent: nameOf(el), candidates: candidates(el), url: location.href });
    },
    true
  );

  window.addEventListener("pagehide", flush, true);
})();
