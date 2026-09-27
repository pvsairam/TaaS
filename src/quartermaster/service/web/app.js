// Quartermaster web UI. Plain JavaScript, no build step: served as-is by `qm serve`.
"use strict";

// ================================================================== helpers

// h("div", {class: "x", onclick: fn}, "text", child, [more]) builds DOM without innerHTML,
// so names and messages from test files are always shown as text.
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

// The same for SVG (charts).
function s(tag, attrs, ...children) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

function setAttrs(el, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected" || k === "open") el[k] = Boolean(v);
    else el.setAttribute(k, v === true ? "" : v);
  }
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : String(c));
  }
}

// Icons: fixed, trusted SVG paths (never user text).
const ICONS = {
  home: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  play: '<circle cx="12" cy="12" r="9"/><path d="M10 8.5l5 3.5-5 3.5z"/>',
  list: '<path d="M10 6h10M10 12h10M10 18h10"/><path d="M3.5 6l1.2 1.2L7 5M3.5 12l1.2 1.2L7 11M3.5 18l1.2 1.2L7 17"/>',
  alert: '<path d="M12 3.5l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
  record: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5" fill="currentColor"/>',
  sliders: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6L6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  minus: '<path d="M6 12h12"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  loader: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
  right: '<path d="M9 6l6 6-6 6"/>',
  left: '<path d="M15 6l-6 6 6 6"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-2.5z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8M15 7h6v6"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 17l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/>',
};

function icon(name, cls) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  el.setAttribute("viewBox", "0 0 24 24");
  el.setAttribute("class", "i" + (cls ? " " + cls : ""));
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = ICONS[name] || "";
  return el;
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `The service answered ${res.status}`);
  return data;
}

function remember(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem("qm." + key) || "null");
    localStorage.setItem("qm." + key, JSON.stringify(value));
  } catch (e) { return null; }
  return value;
}

let toastTimer;
function toast(text) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 4200);
}

const LABELS = {
  queued: "Waiting", running: "Running", passed: "Passed", failed: "Failed", error: "Could not run",
  cancelled: "Cancelled", healed: "Passed, needs update", skipped: "Not done", waiting: "Not started", never: "Never run",
};
const STATUS_ICON = {
  passed: "check", healed: "wrench", failed: "x", error: "alert", running: "loader", queued: "clock",
  cancelled: "minus", skipped: "minus", waiting: "minus", never: "minus",
};

function pill(status, text) {
  return h("span", {class: "pill s-" + status},
    icon(STATUS_ICON[status] || "minus", status === "running" ? "spin" : ""), text || LABELS[status] || status);
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const time = d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  if (days === 0) return `Today, ${time}`;
  if (days === 1) return `Yesterday, ${time}`;
  return `${d.toLocaleDateString([], {day: "numeric", month: "short", year: days > 300 ? "numeric" : undefined})}, ${time}`;
}

function shortDate(iso) {
  return iso ? new Date(iso).toLocaleDateString([], {day: "numeric", month: "short"}) : "";
}

function clock(iso) {
  return iso ? new Date(iso).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : "";
}

function took(start, end) {
  if (!start) return "";
  const sec = Math.max(0, Math.round(((end ? new Date(end) : new Date()) - new Date(start)) / 1000));
  if (sec < 60) return `${sec} s`;
  const m = Math.floor(sec / 60);
  return m < 60 ? `${m} min ${sec % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

function testName(target) {
  if (!target || target === ".") return "All tests";
  const t = state.tests.find((x) => x.file === target);
  if (t && t.title) return t.title;
  return /\.ya?ml$/.test(target) ? target : `All tests in ${target}`;
}

function active(run) {
  return run.status === "queued" || run.status === "running";
}

function testLink(file) {
  return "#/tests/" + encodeURIComponent(file);
}

// ================================================================== state and shell

const state = {status: null, tests: [], attention: 0, timer: null, open: new Set(), page: ""};
const main = document.getElementById("main");

const PAGES = [
  {id: "", label: "Overview", icon: "home"},
  {id: "runs", label: "Runs", icon: "play"},
  {id: "tests", label: "Tests", icon: "list"},
  {id: "attention", label: "Needs attention", icon: "alert"},
  {id: "record", label: "Record a test", icon: "record"},
  {id: "settings", label: "Settings", icon: "sliders"},
];

function show(crumbs, ...children) {
  document.getElementById("crumbs").replaceChildren(...crumbs.flatMap((c, i) => [
    i ? icon("right") : null,
    c.href ? h("a", {href: c.href}, c.label) : h("b", {}, c.label),
  ].filter(Boolean)));
  const animate = main.dataset.page !== location.hash;
  main.dataset.page = location.hash;
  main.replaceChildren(h("div", {}, children));
  if (animate) {
    main.classList.remove("enter");
    void main.offsetWidth;
    main.classList.add("enter");
  }
}

function schedule(fn, ms) {
  clearTimeout(state.timer);
  state.timer = setTimeout(fn, ms);
}

function renderNav() {
  const current = location.hash.replace(/^#\/?/, "").split("/")[0];
  document.getElementById("nav").replaceChildren(...PAGES.map((p) =>
    h("a", {href: "#/" + p.id, class: current === p.id ? "on" : null},
      icon(p.icon), p.label,
      p.id === "attention" && state.attention ? h("span", {class: "badge"}, state.attention) : null)));
}

function renderFoot() {
  const st = state.status;
  if (!st) return;
  let host = st.pod_url;
  try { host = st.pod_url ? new URL(st.pod_url).host.split(".")[0] : ""; } catch (e) { /* keep as typed */ }
  document.getElementById("side-foot").replaceChildren(
    h("a", {class: "pod", href: "#/settings"}, h("span", {class: "dot" + (st.ready ? " ok" : "")}),
      h("span", {}, h("span", {class: "small muted"}, st.ready ? "Connected to pod" : "Not set up"),
        h("b", {}, st.ready ? host : "Open Settings"))));
}

async function loadCommon() {
  const [status, tests, attention] = await Promise.all([
    api("/api/status"), api("/api/tests"), api("/api/attention").catch(() => ({count: 0})),
  ]);
  state.status = status;
  state.tests = tests;
  state.attention = attention.count;
  renderNav();
  renderFoot();
  return attention;
}

function setTheme(theme) {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  remember("theme", theme === "system" ? null : theme);
  drawThemeButton();
}

function currentTheme() {
  const t = document.documentElement.dataset.theme;
  if (t) return t;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function drawThemeButton() {
  const dark = currentTheme() === "dark";
  const b = document.getElementById("theme-btn");
  b.replaceChildren(icon(dark ? "sun" : "moon"));
  b.title = dark ? "Switch to light" : "Switch to dark";
}

function initShell() {
  document.getElementById("menu-btn").append(icon("menu"));
  document.getElementById("menu-btn").onclick = () => document.body.classList.toggle("menu-open");
  document.getElementById("side-scrim").onclick = () => document.body.classList.remove("menu-open");
  const search = document.getElementById("search-btn");
  search.append(icon("search"), h("span", {}, "Search tests and pages"), h("kbd", {}, "Ctrl K"));
  search.onclick = openPalette;
  document.getElementById("theme-btn").onclick = () => setTheme(currentTheme() === "dark" ? "light" : "dark");
  drawThemeButton();
  const newRun = document.getElementById("new-run-btn");
  newRun.append(icon("plus"), h("span", {}, "New run"));
  newRun.onclick = () => openRunDrawer();
  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPalette(); }
    else if (!typing && e.key === "/") { e.preventDefault(); openPalette(); }
    else if (!typing && e.key.toLowerCase() === "n" && !e.ctrlKey && !e.metaKey && !document.querySelector(".scrim")) {
      e.preventDefault(); openRunDrawer();
    }
  });
}

// ================================================================== overlays

function overlay(build, onClose) {
  const scrim = h("div", {class: "scrim"});
  let panel;
  const close = () => {
    scrim.remove(); panel.remove();
    document.removeEventListener("keydown", esc);
    if (onClose) onClose();
  };
  const esc = (e) => { if (e.key === "Escape") close(); };
  panel = build(close);
  scrim.onclick = close;
  document.addEventListener("keydown", esc);
  document.body.append(scrim, panel);
  return close;
}

function seg(options, value, onchange) {
  const box = h("div", {class: "seg", role: "radiogroup"});
  const draw = (v) => box.replaceChildren(...options.map(([val, label]) =>
    h("button", {type: "button", role: "radio", "aria-checked": String(val === v), class: val === v ? "on" : null,
      onclick: () => { draw(val); onchange(val); }}, label)));
  draw(value);
  return box;
}

// The one place a run is started from: all tests, a folder, or one test, with its options.
function openRunDrawer(preset) {
  if (!state.status) return;
  const saved = remember("options") || {};
  const opt = {...state.status.default_options, ...saved, evidence_doc: true};
  const folders = [...new Set(state.tests.map((t) => t.folder).filter(Boolean))].sort();
  const runnable = state.tests.filter((t) => !t.problem);
  let scope = preset ? (/\.ya?ml$/.test(preset) ? "one" : preset === "." ? "all" : "folder") : "all";

  const folderSel = h("select", {}, folders.map((f) =>
    h("option", {value: f}, `${f} (${plural(state.tests.filter((t) => t.folder === f).length, "test")})`)));
  const testSel = h("select", {}, runnable.map((t) => h("option", {value: t.file}, t.title || t.file)));
  if (scope === "folder") folderSel.value = preset;
  if (scope === "one") testSel.value = preset;
  const pick = h("div", {});
  const count = h("span", {class: "muted small"});
  const drawPick = () => {
    pick.replaceChildren(scope === "folder" ? folderSel : scope === "one" ? testSel : h("div", {class: "hint"},
      `Runs every test in ${state.status.tests_folder}.`));
    const n = scope === "all" ? runnable.length : scope === "folder" ? runnable.filter((t) => t.folder === folderSel.value).length : 1;
    count.textContent = plural(n, "test") + " will run";
  };
  folderSel.onchange = drawPick;
  const release = h("input", {type: "text", value: opt.release || "", placeholder: "e.g. 26C"});
  const tester = h("input", {type: "text", value: opt.tester || "", placeholder: "Shown as Run by in the documents"});
  const headed = h("input", {type: "checkbox", checked: opt.headed});
  const ready = state.status.ready;

  overlay((close) => {
    const start = h("button", {class: "btn primary", disabled: !ready || !runnable.length, onclick: async () => {
      const target = scope === "all" ? "." : scope === "folder" ? folderSel.value : testSel.value;
      const options = {screenshots: opt.screenshots, video: opt.video, headed: headed.checked,
        release: release.value.trim(), tester: tester.value.trim(), evidence_doc: true};
      remember("options", options);
      start.disabled = true;
      try {
        const run = await api("/api/runs", {target, options});
        close();
        location.hash = `#/runs/${run.id}`;
      } catch (e) { toast(e.message); start.disabled = false; }
    }}, icon("play"), "Start run");
    drawPick();
    return h("div", {class: "drawer", role: "dialog", "aria-label": "New run"},
      h("div", {class: "drawer-head"}, h("div", {}, h("h2", {}, "New test run"),
        h("div", {class: "muted small"}, "Runs wait in line and go one at a time.")),
        h("button", {class: "icon-btn", onclick: close, "aria-label": "Close"}, icon("x"))),
      h("div", {class: "drawer-body"},
        ready ? null : h("div", {class: "notice bad"}, icon("alert"), h("div", {class: "body"},
          "The Oracle pod or its sign-in is not set up yet. ", h("a", {href: "#/settings", onclick: close}, "Open Settings"))),
        h("div", {}, h("label", {class: "f"}, "What to test"),
          seg([["all", "All tests"], ["folder", "A folder"], ["one", "One test"]], scope, (v) => { scope = v; drawPick(); }),
          h("div", {style: "margin-top:10px"}, pick)),
        h("div", {}, h("label", {class: "f"}, "Pictures of the screen"),
          seg([["every-step", "After every step"], ["on-failure", "Only when a step fails"], ["off", "None"]],
            opt.screenshots, (v) => { opt.screenshots = v; }),
          h("div", {class: "hint"}, "Pictures go into the Word evidence document for each test.")),
        h("div", {}, h("label", {class: "f"}, "Video"),
          seg([["off", "None"], ["on-failure", "Keep when a test fails"], ["always", "Always keep"]],
            opt.video, (v) => { opt.video = v; }),
          h("div", {class: "hint"}, "Videos are saved next to the document, not inside it.")),
        h("div", {class: "fields"},
          h("div", {}, h("label", {class: "f"}, "Oracle release"), release),
          h("div", {}, h("label", {class: "f"}, "Your name"), tester)),
        h("label", {class: "switch"}, headed, "Show the browser while it runs")),
      h("div", {class: "drawer-foot"}, count, h("div", {style: "flex:1"}), h("button", {class: "btn", onclick: close}, "Cancel"), start));
  });
}

// Search and go: pages, actions, tests and recent runs.
async function openPalette() {
  if (document.querySelector(".palette")) return;
  const items = [
    ...PAGES.map((p) => ({group: "Pages", label: p.label, icon: p.icon, go: () => { location.hash = "#/" + p.id; }})),
    {group: "Actions", label: "Start a new run", icon: "plus", hint: "N", go: () => openRunDrawer()},
    {group: "Actions", label: "Run all tests", icon: "play", go: () => openRunDrawer(".")},
    {group: "Actions", label: "Record a new test", icon: "record", go: () => { location.hash = "#/record"; }},
    {group: "Actions", label: "Switch light or dark", icon: "moon", go: () => setTheme(currentTheme() === "dark" ? "light" : "dark")},
    ...state.tests.map((t) => ({group: "Tests", label: t.title || t.file, hint: t.module || t.folder, icon: "file",
      go: () => { location.hash = testLink(t.file); }})),
  ];
  let sel = 0;
  let shown = items;
  const input = h("input", {type: "search", placeholder: "Search tests, runs and pages…", "aria-label": "Search"});
  const list = h("ul", {role: "listbox"});
  let closeFn;
  const draw = () => {
    const q = input.value.trim().toLowerCase();
    shown = q ? items.filter((i) => (i.label + " " + (i.hint || "")).toLowerCase().includes(q)) : items;
    sel = Math.min(sel, Math.max(shown.length - 1, 0));
    let group = "";
    const rows = [];
    shown.forEach((it, n) => {
      if (it.group !== group) { group = it.group; rows.push(h("li", {class: "group"}, group)); }
      rows.push(h("li", {class: n === sel ? "on" : null, role: "option", onmousemove: () => { if (sel !== n) { sel = n; draw(); } },
        onclick: () => { closeFn(); it.go(); }}, icon(it.icon), it.label, it.hint ? h("span", {class: "s"}, it.hint) : null));
    });
    list.replaceChildren(...(rows.length ? rows : [h("li", {class: "group"}, "Nothing matches")]));
    list.querySelector("li.on")?.scrollIntoView({block: "nearest"});
  };
  input.oninput = () => { sel = 0; draw(); };
  input.onkeydown = (e) => {
    if (e.key === "ArrowDown") { sel = Math.min(sel + 1, shown.length - 1); draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); draw(); e.preventDefault(); }
    else if (e.key === "Enter" && shown[sel]) { closeFn(); shown[sel].go(); }
  };
  closeFn = overlay(() => h("div", {class: "palette", role: "dialog", "aria-label": "Search"}, input, list));
  draw();
  input.focus();
  // recent runs arrive a moment later; the palette is usable straight away
  const runs = await api("/api/runs").catch(() => []);
  items.push(...runs.slice(0, 8).map((r) => ({group: "Recent runs", label: testName(r.target), hint: when(r.created_at), icon: "play",
    go: () => { location.hash = `#/runs/${r.id}`; }})));
  if (list.isConnected) draw();
}

// Full-size pictures with previous / next.
function openLightbox(pictures, start) {
  let n = start;
  const img = h("img", {alt: ""});
  const caption = h("div", {class: "grow"});
  const counter = h("span", {class: "small", style: "opacity:.7"});
  const original = h("a", {class: "icon-btn", target: "_blank", title: "Open the original picture"}, icon("external"));
  const draw = () => {
    const p = pictures[n];
    img.src = p.src; img.alt = p.caption;
    caption.replaceChildren(h("b", {}, p.caption), p.sub ? h("div", {class: "small", style: "opacity:.75"}, p.sub) : null);
    counter.textContent = `${n + 1} of ${pictures.length}`;
    original.href = p.src;
  };
  const go = (d) => { n = (n + d + pictures.length) % pictures.length; draw(); };
  const box = h("div", {class: "lightbox", role: "dialog", "aria-label": "Pictures"});
  const keys = (e) => {
    if (e.key === "ArrowRight") go(1);
    else if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "Escape") close();
  };
  const close = () => { box.remove(); document.removeEventListener("keydown", keys); };
  box.append(
    h("div", {class: "bar"}, caption, counter, original, h("button", {class: "icon-btn", onclick: close, "aria-label": "Close"}, icon("x"))),
    h("div", {class: "stage", onclick: (e) => { if (e.target.classList.contains("stage")) close(); }}, img),
    pictures.length > 1 ? h("button", {class: "nav-btn prev", onclick: () => go(-1), "aria-label": "Previous"}, icon("left")) : null,
    pictures.length > 1 ? h("button", {class: "nav-btn next", onclick: () => go(1), "aria-label": "Next"}, icon("right")) : null);
  document.addEventListener("keydown", keys);
  document.body.append(box);
  draw();
}

// ================================================================== charts

const tip = document.getElementById("tip");
function showTip(e, title, rows) {
  tip.replaceChildren(h("div", {class: "tt"}, title), ...rows.map((r) =>
    h("div", {class: "tr"}, h("i", {style: `background:${r.color}`}), r.label, h("b", {}, r.value))));
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
  const y = Math.max(8, e.clientY - tip.offsetHeight - 12);
  tip.style.left = x + "px"; tip.style.top = y + "px";
  tip.classList.add("show");
}
function hideTip() { tip.classList.remove("show"); }

function niceMax(v) {
  if (v <= 5) return 5;
  const step = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= v) return m * step;
  return 10 * step;
}

// Tests passed and failed in each recent run: stacked columns, passed at the base.
function runsChart(trend) {
  const narrow = main.clientWidth < 600; // draw at phone size so the text stays readable
  const W = narrow ? 360 : 640, H = 220, L = 30, R = 8, T = 18, B = 26;
  const max = niceMax(Math.max(...trend.map((t) => t.total), 1));
  const slot = (W - L - R) / Math.max(trend.length, 1);
  const bw = Math.min(24, slot * 0.62);
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const sameDay = new Set(trend.map((t) => shortDate(t.at))).size === 1; // then label the columns by time
  const svg = s("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Tests passed and failed in each recent run"});
  for (let i = 0; i <= 4; i++) {
    const v = (max / 4) * i;
    svg.append(s("line", {class: "gridline", x1: L, x2: W - R, y1: y(v), y2: y(v)}),
      s("text", {class: "axis", x: L - 8, y: y(v) + 4, "text-anchor": "end"}, Number.isInteger(v) ? v : v.toFixed(1)));
  }
  const col = getComputedStyle(document.documentElement);
  const cPass = col.getPropertyValue("--s-pass").trim(), cFail = col.getPropertyValue("--s-fail").trim();
  trend.forEach((t, i) => {
    const cx = L + slot * i + slot / 2, x = cx - bw / 2;
    const g = s("g", {});
    const passTop = y(t.passed), base = y(0);
    // passed from the baseline; failed on top with a 2px gap; rounded only at the data end
    if (t.passed) g.append(s("path", {class: "bar", fill: "var(--s-pass)", d: colPath(x, passTop, bw, base - passTop, !t.failed)}));
    if (t.failed) {
      const top = y(t.total), bottom = t.passed ? passTop - 2 : base;
      g.append(s("path", {class: "bar", fill: "var(--s-fail)", d: colPath(x, top, bw, Math.max(bottom - top, 1), true)}));
    }
    const hit = s("rect", {class: "hit", x: cx - slot / 2, y: T, width: slot, height: H - T - B, tabindex: 0,
      "aria-label": `${shortDate(t.at)}: ${t.passed} passed, ${t.failed} failed`});
    const show = (e) => { g.classList.add("hover"); showTip(e, when(t.at), [
      {color: cPass, label: "Passed", value: t.passed}, {color: cFail, label: "Failed", value: t.failed}]); };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("focus", (e) => { const r = hit.getBoundingClientRect(); show({clientX: r.x + r.width / 2, clientY: r.y + 40}); });
    hit.addEventListener("pointerleave", () => { g.classList.remove("hover"); hideTip(); });
    hit.addEventListener("blur", () => { g.classList.remove("hover"); hideTip(); });
    hit.addEventListener("click", () => { hideTip(); location.hash = `#/runs/${t.run_id}`; });
    svg.append(hit, g);
    if (i === 0 || i === trend.length - 1 || trend.length <= (narrow ? 4 : 8)) {
      svg.append(s("text", {class: "axis", x: cx, y: H - 8, "text-anchor": "middle"}, sameDay ? clock(t.at) : shortDate(t.at)));
    }
  });
  const last = trend[trend.length - 1];
  if (last) {
    const cx = L + slot * (trend.length - 1) + slot / 2;
    svg.append(s("text", {class: "val", x: cx, y: y(last.total) - 6, "text-anchor": "middle"}, `${last.passed}/${last.total}`));
  }
  return h("div", {class: "chart"}, svg);
}

function colPath(x, y, w, hgt, roundTop) {
  const r = roundTop ? Math.min(4, w / 2, hgt) : 0;
  return `M${x},${y + hgt} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + hgt} Z`;
}

function legend(items) {
  return h("div", {class: "legend"}, items.map(([c, l]) => h("span", {}, h("i", {style: `background:var(${c})`}), l)));
}

// ================================================================== Overview

async function dashboardPage() {
  const [attention, dash, runs] = await Promise.all([loadCommon(), api("/api/dashboard"), api("/api/runs")]);
  if (state.page !== "") return;
  const st = state.status;
  const hasRuns = runs.length > 0;
  const latestSummary = runs.find((r) => r.summary_url);

  const tiles = h("div", {class: "grid g4"},
    h("div", {class: "card hero"}, h("div", {class: "stat"},
      h("span", {class: "label"}, icon("shield"), "Passing on their last run"),
      h("span", {class: "value num"}, dash.pass_rate === null ? "–" : `${dash.pass_rate}%`),
      h("span", {class: "sub"}, dash.tested ? `${dash.passing} of ${plural(dash.tested, "test")} passed` : "No tests have run yet")),
      dash.tested ? h("div", {class: "meter", style: "margin-top:14px", title: `${dash.passing} passed, ${dash.failing} failed`},
        dash.passing ? h("span", {style: `width:${100 * dash.passing / dash.tested}%;background:var(--s-pass)`}) : null,
        dash.failing ? h("span", {style: `width:${100 * dash.failing / dash.tested}%;background:var(--s-fail)`}) : null) : null),
    statCard("list", "Tests", dash.tests, `${plural(dash.tests - dash.tested, "test")} never run`, "#/tests"),
    statCard("alert", "Needs attention", attention.count,
      attention.count ? `${attention.failing.length} failed, ${attention.updates.length} to update` : "All clear", "#/attention"),
    statCard("calendar", "Runs this week", dash.runs_this_week, `${plural(dash.tests_run_this_week, "test")} run, ${plural(dash.documents, "document")} in total`, "#/runs"));

  const chartCard = h("div", {class: "card"},
    h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Recent runs"), h("p", {}, "Tests passed and failed in each run. Click a column to open the run.")),
      legend([["--s-pass", "Passed"], ["--s-fail", "Failed"]])),
    dash.trend.length ? runsChart(dash.trend) : emptyState("trend", "No finished runs yet", "Start a run and the results appear here."));

  const attentionCard = h("div", {class: "card flush"},
    h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Needs attention"), h("p", {}, "What to look at first")),
      attention.count ? h("a", {class: "btn sm", href: "#/attention"}, "See all") : null),
    attention.count ? h("div", {class: "list"},
      attention.failing.slice(0, 3).map((f) => h("a", {class: "item", href: `#/runs/${f.run_id}`},
        h("span", {class: "ico bad"}, icon("x")), h("div", {class: "grow"}, h("div", {class: "t"}, f.title),
          h("div", {class: "s"}, `Step ${f.step}: ${f.error || f.intent}`)))),
      attention.updates.slice(0, 2).map((u) => h("a", {class: "item", href: "#/attention"},
        h("span", {class: "ico warn"}, icon("wrench")), h("div", {class: "grow"}, h("div", {class: "t"}, u.title),
          h("div", {class: "s"}, `Step ${u.step} needs an update`)))),
      attention.broken.slice(0, 2).map((b) => h("a", {class: "item", href: "#/tests"},
        h("span", {class: "ico bad"}, icon("file")), h("div", {class: "grow"}, h("div", {class: "t"}, b.file),
          h("div", {class: "s"}, "This test file could not be read")))))
      : h("div", {style: "padding:0 20px 20px"}, emptyState("check", "Nothing needs attention", "Every test passed on its last run.", "good")));

  const modulesCard = h("div", {class: "card"},
    h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "By module"), h("p", {}, "Last result of each test")),
      legend([["--s-pass", "Passing"], ["--s-fail", "Failing"], ["--s-none", "Not run"]])),
    dash.modules.length ? dash.modules.map((m) => {
      const part = (n, c, label) => n ? h("span", {style: `width:${100 * n / m.tests}%;background:var(${c})`,
        onpointermove: (e) => showTip(e, m.module, [{color: getComputedStyle(document.documentElement).getPropertyValue(c), label, value: n}]),
        onpointerleave: hideTip}) : null;
      return h("div", {class: "hbar"}, h("span", {}, m.module), h("div", {class: "track", role: "img",
        "aria-label": `${m.module}: ${m.passing} passing, ${m.failing} failing, ${m.not_run} not run`},
        part(m.passing, "--s-pass", "Passing"), part(m.failing, "--s-fail", "Failing"), part(m.not_run, "--s-none", "Not run")),
        h("span", {class: "num muted", style: "text-align:right"}, `${m.passing}/${m.tests}`));
    }) : emptyState("list", "No tests yet", ""));

  const recentCard = h("div", {class: "card flush"},
    h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Latest runs"), h("p", {}, "Newest first")),
      h("a", {class: "btn sm", href: "#/runs"}, "All runs")),
    hasRuns ? h("div", {class: "list"}, runs.slice(0, 5).map((r) => runItem(r))) :
      h("div", {style: "padding:0 20px 20px"}, emptyState("play", "No runs yet", "Start your first run with New run.")));

  show([{label: "Overview"}],
    h("div", {class: "head"},
      h("div", {}, h("h1", {}, "Overview"), h("p", {}, st.ready ? "How your Oracle Fusion tests are doing, and what needs a look." :
        "Welcome. Three steps get you from nothing to signed evidence.")),
      h("div", {class: "row"},
        latestSummary ? h("a", {class: "btn", href: latestSummary.summary_url}, icon("download"), "Latest summary") : null,
        h("button", {class: "btn primary", onclick: () => openRunDrawer("."), disabled: !st.ready}, icon("play"), "Run all tests"))),
    !hasRuns ? onboarding() : null,
    tiles,
    h("div", {class: "grid g3", style: "margin-top:16px"}, chartCard, attentionCard),
    h("div", {class: "grid g2", style: "margin-top:16px"}, modulesCard, recentCard));

  if (runs.some(active)) schedule(dashboardPage, 3000);
}

function statCard(ic, label, value, sub, href) {
  return h("a", {class: "card", href, style: "color:inherit;text-decoration:none"}, h("div", {class: "stat"},
    h("span", {class: "label"}, icon(ic), label), h("span", {class: "value num"}, value), h("span", {class: "sub"}, sub)));
}

function emptyState(ic, title, text, tone) {
  return h("div", {class: "empty"}, h("div", {class: "ico " + (tone || "idle")}, icon(ic)), h("h3", {}, title), text ? h("p", {}, text) : null);
}

function onboarding() {
  const st = state.status;
  const step = (done, n, title, text, action) => h("div", {class: "item", style: "border-top:0;padding:10px 0"},
    h("span", {class: "ico " + (done ? "good" : "info")}, done ? icon("check") : h("b", {}, n)),
    h("div", {class: "grow"}, h("div", {class: "t"}, title), h("div", {class: "s"}, text)), action);
  return h("div", {class: "card", style: "margin-bottom:16px"},
    h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Get started"), h("p", {}, "Nothing is changed in Oracle unless a test says so."))),
    step(st.ready, 1, "Connect to your Oracle pod", st.ready ? `Using ${st.pod_url}` : "Set the pod address, user and password on this computer.",
      st.ready ? null : h("a", {class: "btn sm", href: "#/settings"}, "How")),
    step(state.tests.length > 0, 2, "Add tests", state.tests.length ? `${plural(state.tests.length, "test")} ready` : "Record one by doing the steps yourself.",
      h("a", {class: "btn sm", href: "#/record"}, icon("record"), "Record")),
    step(false, 3, "Run them and collect the evidence", "Every run makes a Word document per test and a summary.",
      h("button", {class: "btn sm primary", disabled: !st.ready, onclick: () => openRunDrawer(".")}, icon("play"), "Run")));
}

function runItem(r) {
  const c = r.counts;
  return h("a", {class: "item", href: `#/runs/${r.id}`},
    h("span", {class: "ico " + ({passed: "good", failed: "bad", error: "bad", running: "info"}[r.status] || "idle")},
      icon(STATUS_ICON[r.status] || "minus", r.status === "running" ? "spin" : "")),
    h("div", {class: "grow"}, h("div", {class: "t"}, testName(r.target)),
      h("div", {class: "s"}, when(r.started_at || r.created_at), c ? ` · ${c.passed} of ${c.total} passed` : "",
        r.options.tester ? ` · ${r.options.tester}` : "")),
    pill(r.status));
}

// ================================================================== Runs

let runsFilter = {q: "", status: "all"};

async function runsPage() {
  const [, runs] = await Promise.all([loadCommon(), api("/api/runs")]);
  if (state.page !== "runs") return;
  const body = h("div", {});
  const draw = () => {
    const q = runsFilter.q.toLowerCase();
    const shown = runs.filter((r) => (runsFilter.status === "all" || r.status === runsFilter.status ||
      (runsFilter.status === "active" && active(r))) &&
      (!q || (testName(r.target) + " " + r.target + " " + (r.options.tester || "") + " " + (r.options.release || "")).toLowerCase().includes(q)));
    body.replaceChildren(shown.length ? h("div", {class: "table-wrap"}, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Result"), h("th", {}, "What was tested"), h("th", {}, "Tests passed"),
        h("th", {class: "hide-sm"}, "Started"), h("th", {class: "hide-sm"}, "Took"), h("th", {class: "hide-sm"}, "Release"), h("th", {}, ""))),
      h("tbody", {}, shown.map((r) => h("tr", {class: "link", onclick: () => { location.hash = `#/runs/${r.id}`; }},
        h("td", {}, pill(r.status)),
        h("td", {}, h("div", {class: "t"}, testName(r.target)), h("div", {class: "s"}, r.options.tester ? `Run by ${r.options.tester}` : r.target)),
        h("td", {class: "num"}, r.counts ? h("div", {}, `${r.counts.passed} of ${r.counts.total}`,
          h("div", {class: "meter", style: "width:90px;height:5px;margin-top:5px"},
            r.counts.passed ? h("span", {style: `width:${100 * r.counts.passed / r.counts.total}%;background:var(--s-pass)`}) : null,
            r.counts.failed ? h("span", {style: `width:${100 * r.counts.failed / r.counts.total}%;background:var(--s-fail)`}) : null)) :
          h("span", {class: "muted"}, "–")),
        h("td", {class: "hide-sm"}, when(r.started_at || r.created_at)),
        h("td", {class: "hide-sm num"}, r.started_at ? took(r.started_at, r.finished_at) : ""),
        h("td", {class: "hide-sm"}, r.options.release || ""),
        h("td", {style: "text-align:right"}, r.summary_url ? h("a", {class: "btn sm", href: r.summary_url, title: "Download the summary document",
          onclick: (e) => e.stopPropagation()}, icon("download"), h("span", {class: "hide-sm"}, "Summary")) : null)))))) :
      emptyState("play", runs.length ? "No runs match" : "No runs yet", runs.length ? "Try another search or filter." : "Start one with New run."));
  };
  const chips = h("div", {class: "chips"});
  const drawChips = () => chips.replaceChildren(...[["all", "All"], ["active", "In progress"], ["passed", "Passed"], ["failed", "Failed"], ["error", "Could not run"]]
    .map(([v, l]) => h("button", {class: "chip" + (runsFilter.status === v ? " on" : ""), onclick: () => { runsFilter.status = v; drawChips(); draw(); }},
      l, v === "all" ? ` ${runs.length}` : "")));
  drawChips();
  draw();
  show([{label: "Runs"}],
    h("div", {class: "head"}, h("div", {}, h("h1", {}, "Runs"), h("p", {}, "Every run, newest first. Open one to follow it step by step and get its evidence.")),
      h("button", {class: "btn primary", onclick: () => openRunDrawer()}, icon("plus"), "New run")),
    h("div", {class: "toolbar"}, h("div", {class: "search"}, icon("search"),
      h("input", {type: "search", placeholder: "Search by test, person or release", value: runsFilter.q,
        oninput: (e) => { runsFilter.q = e.target.value; draw(); }})), chips),
    h("div", {class: "card flush"}, body));
  if (runs.some(active)) schedule(runsPage, 2500);
}

// ================================================================== one run

// Turn the run's progress events into one entry per test with its steps.
function progress(events) {
  const tests = new Map();
  const get = (id) => {
    if (!tests.has(id)) {
      const known = state.tests.find((t) => t.id === id);
      tests.set(id, {id, title: (known && known.title) || id, steps: [], status: "waiting", total: (known && known.steps) || 0});
    }
    return tests.get(id);
  };
  for (const e of events) {
    if (e.type === "suite_start") (e.tests || []).forEach(get);
    else if (e.type === "run_start") Object.assign(get(e.test_id), {title: e.title, total: e.steps, status: "running"});
    else if (e.type === "step_start") get(e.test_id).steps[e.index] = {number: e.index + 1, intent: e.intent, status: "running"};
    else if (e.type === "step_end") get(e.test_id).steps[e.index] = {number: e.index + 1, intent: e.intent, status: e.status, error: e.plain_error, detail: e.error};
    else if (e.type === "run_end") get(e.test_id).status = e.status;
  }
  return [...tests.values()];
}

function failureNotice(title, plain, detail) {
  return h("div", {class: "notice bad"}, icon("alert"), h("div", {class: "body"}, h("b", {}, title), plain ? " " + plain : "",
    detail && detail !== plain ? h("details", {}, h("summary", {}, "Details for the test team"), h("pre", {}, detail)) : null));
}

function stepRows(steps, total, pictures) {
  const rows = steps.filter(Boolean).map((st) => h("li", {class: st.status},
    h("span", {class: "mark"}, ["passed", "healed", "failed", "running"].includes(st.status) ?
      icon(STATUS_ICON[st.status], st.status === "running" ? "spin" : "") : st.number),
    h("div", {}, h("div", {}, st.intent || ""),
      st.status === "healed" ? h("div", {class: "small", style: "color:var(--warn)"}, "Found in a different way than written. See Needs attention.") : null,
      st.status === "failed" && st.error ? h("div", {class: "small", style: "color:var(--bad)"}, st.error) : null,
      st.pictures && st.pictures.length ? h("div", {class: "thumbs"}, st.pictures.map((src) => h("img", {class: "thumb", src, loading: "lazy",
        alt: `Screen after step ${st.number}`, onclick: () => openLightbox(pictures, pictures.findIndex((p) => p.src === src))}))) : null),
    h("span", {class: "meta"}, st.status === "skipped" ? "Not done" : st.seconds ? `${st.seconds} s` : "")));
  const left = total - steps.filter(Boolean).length;
  if (left > 0) rows.push(h("li", {class: "waiting"}, h("span", {class: "mark"}, "…"), h("div", {}, `${plural(left, "more step")} to go`), h("span", {})));
  return h("ol", {class: "steps"}, rows);
}

async function runPage(id) {
  if (!state.tests.length) await loadCommon();
  const run = await api(`/api/runs/${encodeURIComponent(id)}`);
  if (location.hash !== `#/runs/${id}`) return; // the page was left while this loaded
  const isActive = active(run);
  const live = progress(run.events);
  const liveById = new Map(live.map((t) => [t.id, t]));
  const outputOpen = document.querySelector("details.output-box")?.open || false;

  // progress over all steps of all tests
  const totals = live.reduce((a, t) => ({done: a.done + t.steps.filter((x) => x && x.status !== "running").length, all: a.all + Math.max(t.total, t.steps.length)}), {done: 0, all: 0});
  const pct = run.status === "queued" ? 0 : isActive ? (totals.all ? Math.round(100 * totals.done / totals.all) : 2) : 100;
  const doneTests = live.filter((t) => !["waiting", "running"].includes(t.status)).length;

  const cancel = isActive ? h("button", {class: "btn danger", onclick: async (ev) => {
    ev.currentTarget.disabled = true;
    await api(`/api/runs/${encodeURIComponent(id)}/cancel`, {}).catch((e) => toast(e.message));
    runPage(id);
  }}, icon("stop"), run.status === "queued" ? "Remove from the line" : "Stop this run") : null;

  const headCard = h("div", {class: "card"},
    h("div", {class: "row", style: "justify-content:space-between;align-items:flex-start"},
      h("div", {style: "min-width:0"}, h("div", {class: "row", style: "margin-bottom:6px"}, pill(run.status)),
        h("h1", {}, testName(run.target)),
        h("div", {class: "muted small", style: "margin-top:4px"}, isActive ? (run.status === "queued" ? "Waiting for the run before it to finish." :
          `${doneTests} of ${plural(live.length, "test")} done · ${pct}%`) :
          run.results.length ? `${run.results.filter((r) => r.status !== "failed").length} of ${plural(run.results.length, "test")} passed` : "")),
      h("div", {class: "row"}, cancel,
        run.suite_folder ? h("button", {class: "btn", onclick: () => openFolder(run.suite_folder)}, icon("folder"), "Open folder") : null,
        run.summary_url ? h("a", {class: "btn primary", href: run.summary_url}, icon("download"), "Summary document") : null)),
    isActive || run.status === "passed" || run.status === "failed" ? h("div", {class: "progress" + (isActive ? " live" : "")},
      h("span", {style: `width:${pct}%`})) : null,
    h("div", {class: "facts"},
      fact("Started", when(run.started_at) || "Not yet"),
      fact("Took", run.started_at ? took(run.started_at, run.finished_at) : "–"),
      fact("Pictures", {"every-step": "After every step", "on-failure": "When a step fails", off: "None"}[run.options.screenshots]),
      fact("Video", {off: "None", "on-failure": "Kept when a test fails", always: "Always"}[run.options.video]),
      run.options.release ? fact("Oracle release", run.options.release) : null,
      run.options.tester ? fact("Run by", run.options.tester) : null));

  let body;
  if (run.results.length) {
    body = run.results.map((r) => resultBlock(r, run.results.length === 1));
  } else if (live.length) {
    body = live.map((t) => h("details", {class: "test-block", open: t.status !== "waiting",
      ontoggle: (e) => rememberOpen(t.id, e.currentTarget.open)},
      h("summary", {}, icon("right", "chev"), h("div", {class: "grow"}, h("h3", {}, t.title),
        h("div", {class: "muted small"}, t.total ? `${t.steps.filter((x) => x && x.status !== "running").length} of ${plural(t.total, "step")}` : "")), pill(t.status)),
      t.status === "waiting" ? null : h("div", {class: "inner"}, stepRows(t.steps, t.total, []))));
  } else {
    body = h("div", {class: "card"}, emptyState(run.status === "queued" ? "clock" : isActive ? "loader" : "minus",
      run.status === "queued" ? "Waiting in line" : isActive ? "Opening the browser and signing in" : "No test results",
      run.status === "queued" ? "It starts when the run before it finishes." : ""));
  }

  show([{label: "Runs", href: "#/runs"}, {label: testName(run.target)}],
    headCard,
    run.status === "error" ? failureNotice("The run could not finish.", run.error || "") : null,
    h("div", {style: "margin-top:16px"}, body),
    run.output ? h("details", {class: "card output-box", open: outputOpen, style: "margin-top:16px"},
      h("summary", {class: "muted"}, "Messages from the run (for the test team)"), h("pre", {class: "output"}, run.output)) : null);

  if (isActive) schedule(() => runPage(id), 1500);
}

function rememberOpen(id, open) {
  if (open) state.open.add(id); else state.open.delete(id);
}

function fact(k, v) {
  return h("div", {}, h("div", {class: "k"}, k), h("div", {class: "v"}, v));
}

function openFolder(path) {
  api("/api/open", {path}).catch((e) => toast(e.message));
}

function resultBlock(r, only) {
  const pictures = r.steps.flatMap((st) => st.pictures.map((src) => ({src, caption: `Step ${st.number}: ${st.intent}`,
    sub: `${r.test_title || r.test_id} · ${LABELS[st.status] || st.status}`})));
  const key = r.folder;
  const open = state.open.has(key) || only || r.status === "failed";
  return h("details", {class: "test-block", open, ontoggle: (e) => rememberOpen(key, e.currentTarget.open)},
    h("summary", {}, icon("right", "chev"),
      h("div", {class: "grow"}, h("h3", {}, r.test_title || r.test_id),
        h("div", {class: "muted small"}, `${r.steps_passed} of ${plural(r.steps_total, "step")} passed · ${r.duration}`,
          pictures.length ? ` · ${plural(pictures.length, "picture")}` : "")),
      pill(r.status)),
    h("div", {class: "inner"},
      r.needs_update ? h("div", {class: "notice warn"}, icon("wrench"), h("div", {class: "body"},
        "This test passed, but something on the screen was found in a different way than when it was written. ",
        h("a", {href: "#/attention"}, "Review the update"), ".")) : null,
      r.failed_step ? failureNotice(`Step ${r.failed_step.number} failed: ${r.failed_step.intent}.`, r.failed_step.error, r.failed_step.detail) : null,
      h("div", {class: "row", style: "margin:4px 0 10px"},
        r.document_url ? h("a", {class: "btn sm primary", href: r.document_url}, icon("file"), "Evidence document") : null,
        pictures.length ? h("button", {class: "btn sm", onclick: () => openLightbox(pictures, 0)}, icon("image"), "View pictures") : null,
        r.videos.map((v, i) => h("a", {class: "btn sm", href: v, target: "_blank"}, icon("video"), r.videos.length > 1 ? `Video ${i + 1}` : "Video")),
        h("button", {class: "btn sm", onclick: () => openFolder(r.folder)}, icon("folder"), "Open folder")),
      stepRows(r.steps, r.steps_total, pictures)));
}

// ================================================================== Tests

let testsFilter = {q: "", module: "all", status: "all"};

function lastStatus(t) {
  return t.last_result ? t.last_result.status : "never";
}

async function testsPage() {
  const attention = await loadCommon();
  if (state.page !== "tests") return;
  const needsUpdate = new Set(attention.updates.map((u) => u.file));
  const modules = [...new Set(state.tests.map((t) => t.module).filter(Boolean))].sort();
  const body = h("div", {});
  const draw = () => {
    const q = testsFilter.q.toLowerCase();
    const shown = state.tests.filter((t) =>
      (testsFilter.module === "all" || t.module === testsFilter.module) &&
      (testsFilter.status === "all" || (testsFilter.status === "update" ? needsUpdate.has(t.file) :
        testsFilter.status === "failing" ? lastStatus(t) === "failed" : testsFilter.status === "never" ? !t.last_result : true)) &&
      (!q || [t.title, t.file, t.id, t.module, t.product, t.process, ...(t.tags || [])].join(" ").toLowerCase().includes(q)));
    body.replaceChildren(shown.length ? h("div", {class: "table-wrap"}, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Test"), h("th", {class: "hide-sm"}, "Module"), h("th", {class: "hide-sm"}, "Steps"),
        h("th", {}, "Last result"), h("th", {}, ""))),
      h("tbody", {}, shown.map((t) => h("tr", {class: "link", onclick: () => { location.hash = testLink(t.file); }},
        h("td", {}, h("div", {class: "t"}, t.title || t.file), h("div", {class: "s"}, t.file),
          t.problem ? h("div", {class: "small", style: "color:var(--bad)"}, t.problem) : null,
          needsUpdate.has(t.file) ? h("div", {class: "small", style: "color:var(--warn)"}, "Needs an update") : null),
        h("td", {class: "hide-sm"}, t.module || "", t.product ? h("div", {class: "s"}, t.product) : null),
        h("td", {class: "hide-sm num"}, t.steps ?? ""),
        h("td", {}, pill(lastStatus(t)), t.last_result ? h("div", {class: "s"}, when(t.last_result.at)) : null),
        h("td", {style: "text-align:right"}, h("button", {class: "btn sm", disabled: !state.status.ready || Boolean(t.problem), title: "Run this test",
          onclick: (e) => { e.stopPropagation(); openRunDrawer(t.file); }}, icon("play"), h("span", {class: "hide-sm"}, "Run")))))))) :
      emptyState("list", state.tests.length ? "No tests match" : "No tests yet", state.tests.length ? "Try another search or filter." : "Record your first test."));
  };
  const chipRow = (list, key, drawFn) => {
    const box = h("div", {class: "chips"});
    const paint = () => box.replaceChildren(...list.map(([v, l]) => h("button", {class: "chip" + (testsFilter[key] === v ? " on" : ""),
      onclick: () => { testsFilter[key] = v; paint(); drawFn(); }}, l)));
    paint();
    return box;
  };
  draw();
  show([{label: "Tests"}],
    h("div", {class: "head"}, h("div", {}, h("h1", {}, "Tests"),
      h("p", {}, `${plural(state.tests.length, "test")} in `, h("code", {}, state.status.tests_folder))),
      h("div", {class: "row"}, h("a", {class: "btn", href: "#/record"}, icon("record"), "Record a test"),
        h("button", {class: "btn primary", disabled: !state.status.ready, onclick: () => openRunDrawer(".")}, icon("play"), "Run all"))),
    h("div", {class: "toolbar"}, h("div", {class: "search"}, icon("search"),
      h("input", {type: "search", placeholder: "Search by name, module, process or tag", value: testsFilter.q,
        oninput: (e) => { testsFilter.q = e.target.value; draw(); }})),
      chipRow([["all", "All"], ["failing", "Failing"], ["update", "Needs update"], ["never", "Never run"]], "status", draw)),
    modules.length > 1 ? h("div", {class: "toolbar"}, chipRow([["all", "All modules"], ...modules.map((m) => [m, m])], "module", draw)) : null,
    h("div", {class: "card flush"}, body));
}

async function testPage(file) {
  const [, t] = await Promise.all([loadCommon(), api("/api/test?file=" + encodeURIComponent(file))]);
  if (location.hash !== testLink(file)) return;
  let tab = remember("testTab") || "steps";
  const panel = h("div", {});
  const ACTIONS = {navigate: "Open", click: "Click", fill: "Type", select: "Choose", assert_text: "Check", assert_visible: "Check",
    login_as: "Sign in as", wait_for: "Wait", upload: "Upload"};
  const tabs = h("div", {class: "tabs", role: "tablist"});
  const drawTab = () => {
    tabs.replaceChildren(...[["steps", "Steps"], ["data", "Test data"], ["history", `History (${t.history.length})`], ["file", "File"]]
      .map(([v, l]) => h("button", {role: "tab", "aria-selected": String(tab === v), class: tab === v ? "on" : null,
        onclick: () => { tab = v; remember("testTab", v); drawTab(); }}, l)));
    if (tab === "steps") {
      panel.replaceChildren(h("ol", {class: "steps"}, t.steps_detail.map((st) => h("li", {},
        h("span", {class: "mark"}, st.number),
        h("div", {}, h("div", {}, h("span", {class: "tag", style: "margin-right:8px"}, ACTIONS[st.action] || st.action), st.intent),
          st.value ? h("div", {class: "small muted", style: "margin-top:3px"}, st.action === "navigate" ? "Page: " : "Value: ", h("code", {}, st.value)) : null,
          st.found_by.length ? h("div", {class: "small muted", style: "margin-top:3px"}, "Found by ", st.found_by[0],
            st.found_by.length > 1 ? `, or else ${st.found_by.slice(1).join(", or ")}` : "") : null),
        h("span", {})))));
    } else if (tab === "data") {
      const keys = Object.keys(t.data || {});
      panel.replaceChildren(keys.length ? h("dl", {class: "kv"}, keys.flatMap((k) => [h("dt", {}, k), h("dd", {}, String(t.data[k]))])) :
        emptyState("list", "No test data", "Values typed by this test are written in its steps."),
        keys.length ? h("p", {class: "hint", style: "margin-top:14px"}, "Steps use these values as ${name}. Change them in the file to test with other data.") : null);
    } else if (tab === "history") {
      panel.replaceChildren(t.history.length ? h("div", {class: "table-wrap"}, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Result"), h("th", {}, "When"), h("th", {}, "Steps passed"), h("th", {class: "hide-sm"}, "Took"), h("th", {}, ""))),
        h("tbody", {}, t.history.map((r) => h("tr", {class: "link", onclick: () => { location.hash = `#/runs/${r.run_id}`; }},
          h("td", {}, pill(r.status)), h("td", {}, when(r.at)), h("td", {class: "num"}, `${r.steps_passed} of ${r.steps_total}`),
          h("td", {class: "hide-sm num"}, r.duration || ""),
          h("td", {style: "text-align:right"}, r.document_url ? h("a", {class: "btn sm", href: r.document_url, onclick: (e) => e.stopPropagation()},
            icon("file"), h("span", {class: "hide-sm"}, "Evidence")) : null)))))) :
        emptyState("clock", "Not run yet", "Run it to start its history."));
    } else {
      panel.replaceChildren(h("div", {class: "row", style: "justify-content:space-between;margin-bottom:10px"},
        h("span", {class: "muted small"}, "The test as written, for the test team. Edit it in any text editor."),
        h("button", {class: "btn sm", onclick: () => navigator.clipboard.writeText(t.yaml).then(() => toast("Copied"), () => toast("Could not copy"))},
          icon("copy"), "Copy")), h("pre", {class: "code"}, t.yaml));
    }
  };
  drawTab();
  const last = t.history[0];
  show([{label: "Tests", href: "#/tests"}, {label: t.title || t.file}],
    h("div", {class: "head"},
      h("div", {style: "min-width:0"}, h("h1", {}, t.title || t.file),
        h("p", {}, [t.module, t.product, t.process].filter(Boolean).join(" · ") || t.file),
        h("div", {class: "row", style: "margin-top:8px"}, (t.tags || []).map((g) => h("span", {class: "tag"}, g)),
          t.persona ? h("span", {class: "tag"}, `Runs as ${t.persona}`) : null, t.priority ? h("span", {class: "tag"}, `Priority: ${t.priority}`) : null)),
      h("button", {class: "btn primary", disabled: !state.status.ready || Boolean(t.problem), onclick: () => openRunDrawer(t.file)}, icon("play"), "Run this test")),
    t.problem ? failureNotice("This file could not be read.", t.problem) : null,
    h("div", {class: "grid g4", style: "margin-bottom:16px"},
      h("div", {class: "card stat"}, h("span", {class: "label"}, "Last result"), h("span", {style: "margin-top:4px"}, last ? pill(last.status) : pill("never")),
        h("span", {class: "sub"}, last ? when(last.at) : "")),
      h("div", {class: "card stat"}, h("span", {class: "label"}, "Passed"), h("span", {class: "value num"}, t.pass_rate === null ? "–" : `${t.pass_rate}%`),
        h("span", {class: "sub"}, `of ${plural(t.history.length, "run")}`)),
      h("div", {class: "card stat"}, h("span", {class: "label"}, "Steps"), h("span", {class: "value num"}, t.steps ?? 0), h("span", {class: "sub"}, t.id)),
      h("div", {class: "card stat"}, h("span", {class: "label"}, "File"), h("span", {style: "font-weight:600;overflow-wrap:anywhere"}, t.file),
        h("span", {class: "sub"}, "in the tests folder"))),
    h("div", {class: "card"}, tabs, panel));
}

// ================================================================== Needs attention

async function attentionPage() {
  const a = await loadCommon();
  if (state.page !== "attention") return;
  const section = (title, sub, items) => items.length ? h("div", {style: "margin-bottom:22px"},
    h("div", {style: "margin-bottom:10px"}, h("h2", {}, title), h("p", {class: "muted small", style: "margin:2px 0 0"}, sub)), items) : null;

  const failing = a.failing.map((f) => h("div", {class: "card", style: "margin-bottom:12px"},
    h("div", {class: "row", style: "justify-content:space-between"},
      h("div", {class: "row", style: "min-width:0;flex:1"}, h("span", {class: "ico bad"}, icon("x")),
        h("div", {style: "min-width:0"}, h("a", {href: testLink(f.file)}, h("h3", {}, f.title)), h("div", {class: "muted small"}, `Failed ${when(f.at).toLowerCase()}`))),
      h("div", {class: "row"}, h("a", {class: "btn sm", href: `#/runs/${f.run_id}`}, "See the run"),
        h("button", {class: "btn sm primary", disabled: !state.status.ready, onclick: () => openRunDrawer(f.file)}, icon("play"), "Run again"))),
    failureNotice(`Step ${f.step}: ${f.intent}.`, f.error)));

  const updates = a.updates.map((u) => h("div", {class: "card", style: "margin-bottom:12px"},
    h("div", {class: "row", style: "justify-content:space-between"},
      h("div", {class: "row", style: "min-width:0;flex:1"}, h("span", {class: "ico warn"}, icon("wrench")),
        h("div", {style: "min-width:0"}, h("a", {href: testLink(u.file)}, h("h3", {}, u.title)),
          h("div", {class: "muted small"}, `Step ${u.step}: ${u.intent}`))),
      h("div", {class: "row"}, h("button", {class: "btn sm primary", onclick: async (ev) => {
        ev.currentTarget.disabled = true;
        try {
          await api("/api/test/accept-update", {file: u.file, step_index: u.step_index, new: u.new});
          toast("Test updated. A copy of the old file was kept.");
          attentionPage();
        } catch (e) { toast(e.message); ev.currentTarget.disabled = false; }
      }}, icon("check"), "Accept update"))),
    h("div", {class: "change"},
      h("div", {}, h("div", {class: "k"}, "Written to find"), u.old_text),
      icon("arrow"),
      h("div", {}, h("div", {class: "k"}, "Found last time by"), u.new_text)),
    h("p", {class: "muted small", style: "margin:0"},
      "Accepting makes the test try the second way first, so it keeps passing after Oracle's quarterly update. A copy of the old file is kept.")));

  const broken = a.broken.map((b) => h("div", {class: "card", style: "margin-bottom:12px"},
    h("div", {class: "row"}, h("span", {class: "ico bad"}, icon("file")), h("div", {style: "min-width:0"}, h("h3", {}, b.file),
      h("div", {class: "muted small", style: "overflow-wrap:anywhere"}, b.problem)))));

  show([{label: "Needs attention"}],
    h("div", {class: "head"}, h("div", {}, h("h1", {}, "Needs attention"),
      h("p", {}, "Tests that failed on their last run, tests that need a small update after an Oracle change, and files that could not be read."))),
    a.count ? [
      section("Failed on their last run", "Check the picture of the failure, fix the test data or report the problem, then run it again.", failing),
      section("Tests to update", "These passed, but something on the screen had changed. One click keeps them reliable.", updates),
      section("Test files that could not be read", "Fix these files in a text editor.", broken),
    ] : h("div", {class: "card"}, emptyState("check", "Nothing needs attention", "Every test passed on its last run, as written.", "good")));
}

// ================================================================== Record

async function recordPage() {
  await loadCommon();
  const rec = await api("/api/recording");
  if (location.hash !== "#/record") return;
  const busy = rec.status === "recording" || rec.status === "saving";

  let status = null;
  if (rec.status === "recording") {
    status = h("div", {class: "card hero", style: "margin-bottom:16px"},
      h("div", {class: "row"}, h("span", {class: "ico bad pulse"}, icon("record")), h("div", {}, h("h2", {}, `Recording "${rec.title}"`),
        h("div", {class: "muted small"}, `Started ${when(rec.started_at).toLowerCase()} · saving to ${rec.file}`))),
      h("ol", {style: "margin:14px 0 0;padding-left:20px;color:var(--text-2)"},
        h("li", {}, "A browser window has opened and signed in to Oracle for you. Do the steps of the test there."),
        h("li", {}, "To record something that must be true, such as a value on the screen, click ", h("b", {}, "Add check"), " in the toolbar in that window, then click the value."),
        h("li", {}, "When you are done, stop here or with ", h("b", {}, "Stop recording"), " in that window.")),
      h("div", {class: "row", style: "margin-top:16px"}, h("button", {class: "btn primary", onclick: async () => {
        await api("/api/recording/stop", {}).catch((e) => toast(e.message));
        recordPage();
      }}, icon("stop"), "Stop recording and save")));
  } else if (rec.status === "saving") {
    status = h("div", {class: "card", style: "margin-bottom:16px"}, h("div", {class: "row"}, h("span", {class: "ico info"}, icon("loader", "spin")),
      h("h2", {}, "Saving the recording…")));
  } else if (rec.status === "saved") {
    status = h("div", {class: "card", style: "margin-bottom:16px"},
      h("div", {class: "row"}, h("span", {class: "ico good"}, icon("check")), h("div", {}, h("h2", {}, "Recording saved"),
        h("div", {class: "muted small"}, rec.message || "", ` It is in ${rec.file}.`))),
      h("div", {class: "row", style: "margin-top:14px"},
        h("button", {class: "btn primary", disabled: !state.status.ready, onclick: () => openRunDrawer(rec.file)}, icon("play"), "Run it now"),
        h("a", {class: "btn", href: testLink(rec.file)}, "Open the test")));
  } else if (rec.status === "error") {
    status = failureNotice("The recording was not saved.", rec.message || "");
  }

  const saved = remember("record") || {};
  const field = (id, label, hint, placeholder, value) => h("div", {},
    h("label", {class: "f", for: "r-" + id}, label),
    h("input", {type: "text", id: "r-" + id, placeholder, value: value || ""}),
    hint ? h("div", {class: "hint"}, hint) : null);
  const idInput = () => document.getElementById("r-id");
  const form = h("div", {class: "card"},
    h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "New recording"), h("p", {}, "Sign-in is done for you and is never recorded."))),
    h("div", {class: "fields"},
      h("div", {class: "wide"}, h("label", {class: "f", for: "r-title"}, "Test name"),
        h("input", {type: "text", id: "r-title", placeholder: "View a worker's details", oninput: (e) => {
          const id = idInput();
          if (id && !id.dataset.touched) id.value = slug(document.getElementById("r-module").value, e.target.value);
        }}), h("div", {class: "hint"}, "What the test checks, in plain words.")),
      field("module", "Module", null, "HCM", saved.module),
      field("product", "Product", null, "Global Human Resources", saved.product),
      field("id", "Test id", "Short and unique. Filled in from the name; change it if you like.", "hcm.view-worker"),
      field("persona", "Job role (optional)", "The role the test runs as.", "HR Specialist", saved.persona),
      h("div", {class: "wide"}, h("label", {class: "f", for: "r-file"}, "Save as (optional)"),
        h("input", {type: "text", id: "r-file", placeholder: "recorded/view_worker.yaml"}),
        h("div", {class: "hint"}, "Inside the tests folder. An existing test is never overwritten."))),
    h("div", {class: "row", style: "margin-top:18px"}, h("button", {class: "btn primary", disabled: busy || !state.status.ready, onclick: async (ev) => {
      const val = (k) => document.getElementById("r-" + k).value.trim();
      const request = {title: val("title"), id: val("id"), module: val("module"), product: val("product"), persona: val("persona"), file: val("file")};
      remember("record", {module: request.module, product: request.product, persona: request.persona});
      ev.currentTarget.disabled = true;
      try { await api("/api/recording", request); } catch (e) { toast(e.message); ev.currentTarget.disabled = false; return; }
      recordPage();
    }}, icon("record"), "Start recording"),
    state.status.ready ? null : h("span", {class: "muted small"}, "Set up the Oracle pod first, in Settings.")));

  const how = h("div", {class: "card"}, h("h2", {style: "margin-bottom:12px"}, "How it works"),
    [["1", "Name the test", "Say what it checks, and which module it belongs to."],
      ["2", "Do the steps once", "Clicks, typing and choices from lists are written down as steps."],
      ["3", "Add checks", "Use Add check on values that must be right, so a replay proves the outcome."],
      ["4", "Replay every quarter", "Run it after each Oracle update. Each run makes Word evidence."]]
      .map(([n, t, d]) => h("div", {class: "item", style: "border-top:0;padding:8px 0"}, h("span", {class: "ico info"}, h("b", {}, n)),
        h("div", {class: "grow"}, h("div", {class: "t"}, t), h("div", {class: "s", style: "white-space:normal"}, d)))),
    h("div", {class: "notice info", style: "margin-top:12px"}, icon("sparkle"), h("div", {class: "body"},
      "Keep tests that are safe to repeat. A test that submits a real record creates one every time it runs.")));

  show([{label: "Record a test"}],
    h("div", {class: "head"}, h("div", {}, h("h1", {}, "Record a test"), h("p", {}, "Create a test by doing the steps yourself, once. No code."))),
    status,
    busy ? null : h("div", {class: "grid g3"}, form, how));
  const id = idInput();
  if (id) id.addEventListener("input", () => { id.dataset.touched = "1"; });
  if (busy) schedule(recordPage, 1500);
}

function slug(module, title) {
  const clean = (x) => x.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const words = clean(title).split("-").filter(Boolean).slice(0, 5).join("-");
  return [clean(module), words].filter(Boolean).join(".");
}

// ================================================================== Settings

async function settingsPage() {
  await loadCommon();
  if (state.page !== "settings") return;
  const st = state.status;
  const row = (name, value, ok) => h("div", {class: "item", style: "padding:12px 0"},
    h("span", {class: "ico " + (ok ? "good" : "bad")}, icon(ok ? "check" : "x")),
    h("div", {class: "grow"}, h("div", {class: "t"}, name), h("div", {class: "s", style: "overflow-wrap:anywhere;white-space:normal"}, value)));
  const theme = document.documentElement.dataset.theme || "system";
  show([{label: "Settings"}],
    h("div", {class: "head"}, h("div", {}, h("h1", {}, "Settings"), h("p", {}, "What this Quartermaster uses. Passwords are never shown."))),
    h("div", {class: "grid g2"},
      h("div", {class: "card"}, h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Oracle pod"), h("p", {}, "Where tests run"))),
        row("Pod address", st.pod_url || "Not set (QM_FUSION_URL)", Boolean(st.pod_url)),
        row("User name", st.user || "Not set (QM_FUSION_USER)", Boolean(st.user)),
        row("Password", st.password_set ? "Set" : "Not set (QM_FUSION_PASSWORD)", st.password_set),
        h("p", {class: "hint", style: "margin-top:12px"}, "These come from environment variables on this computer. To change them, set the variables, stop Quartermaster (Ctrl+C) and run ",
          h("code", {}, "qm serve"), " again. Use a test or development pod only, never production.")),
      h("div", {}, h("div", {class: "card"}, h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Folders"), h("p", {}, "Where things are kept"))),
        h("dl", {class: "kv"}, h("dt", {}, "Tests"), h("dd", {}, h("code", {}, st.tests_folder)),
          h("dt", {}, "Evidence"), h("dd", {}, h("code", {}, st.evidence_folder))),
        h("div", {class: "row", style: "margin-top:14px"}, h("button", {class: "btn sm", onclick: () => openFolder(".")}, icon("folder"), "Open the evidence folder"))),
      h("div", {class: "card"}, h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Appearance"))),
        seg([["system", "Same as this computer"], ["light", "Light"], ["dark", "Dark"]], theme, setTheme)),
      h("div", {class: "card"}, h("div", {class: "card-head"}, h("div", {}, h("h2", {}, "Keyboard shortcuts"))),
        h("dl", {class: "kv"}, h("dt", {}, h("kbd", {}, "Ctrl K"), " or ", h("kbd", {}, "/")), h("dd", {}, "Search tests, runs and pages"),
          h("dt", {}, h("kbd", {}, "N")), h("dd", {}, "Start a new run"),
          h("dt", {}, h("kbd", {}, "←"), " ", h("kbd", {}, "→")), h("dd", {}, "Previous and next picture"),
          h("dt", {}, h("kbd", {}, "Esc")), h("dd", {}, "Close"))))));
}

// ================================================================== routing

async function route() {
  clearTimeout(state.timer);
  hideTip();
  document.body.classList.remove("menu-open");
  const [page, ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  const arg = decodeURIComponent(rest.join("/"));
  state.page = page;
  renderNav();
  try {
    if (page === "runs" && arg) await runPage(arg);
    else if (page === "runs") await runsPage();
    else if (page === "tests" && arg) await testPage(arg);
    else if (page === "tests") await testsPage();
    else if (page === "attention") await attentionPage();
    else if (page === "record") await recordPage();
    else if (page === "settings") await settingsPage();
    else await dashboardPage();
  } catch (e) {
    show([{label: "Problem"}], failureNotice("Something went wrong.", e.message));
  }
}

initShell();
window.addEventListener("hashchange", route);
route();
