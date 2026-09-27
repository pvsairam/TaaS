// Quartermaster web UI. Plain JavaScript, no build step: served as-is by `qm serve`.
"use strict";

// ------------------------------------------------------------------ helpers

// h("div", {class: "x", onclick: fn}, "text", child, [more]) builds DOM without innerHTML,
// so names and messages from test files are always shown as text.
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") el[k] = Boolean(v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : String(c));
  }
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
  toastTimer = setTimeout(() => t.classList.remove("show"), 4000);
}

const LABELS = {
  queued: "Waiting", running: "Running", passed: "Passed", failed: "Failed", error: "Could not run",
  cancelled: "Cancelled", healed: "Passed, test needs an update", skipped: "Not done", waiting: "Not started",
};
const ICONS = {passed: "✓", healed: "✓", failed: "✗", running: "…", skipped: "–", waiting: "·"};

function pill(status) {
  return h("span", {class: "pill s-" + status}, LABELS[status] || status);
}

function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  const time = d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  return today ? `Today ${time}` : `${d.toLocaleDateString([], {day: "numeric", month: "short", year: "numeric"})} ${time}`;
}

function took(start, end) {
  if (!start) return "";
  const s = Math.max(0, Math.round(((end ? new Date(end) : new Date()) - new Date(start)) / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

function targetName(target) {
  if (!target || target === ".") return "All tests";
  const t = state.tests.find((x) => x.file === target);
  if (t && t.title) return t.title;
  return target.endsWith(".yaml") || target.endsWith(".yml") ? target : `Folder: ${target}`;
}

// ------------------------------------------------------------------ app state and routing

const state = {status: null, tests: [], timer: null};
const main = document.getElementById("main");

// Replace the page content. Goes through h() so lists are flattened and empty parts skipped.
function show(...children) {
  main.replaceChildren(h("div", {}, children));
}

function schedule(fn, ms) {
  clearTimeout(state.timer);
  state.timer = setTimeout(fn, ms);
}

async function route() {
  clearTimeout(state.timer);
  const [page, id] = location.hash.replace(/^#\/?/, "").split("/");
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === (page || "runs")));
  try {
    if (page === "tests") await testsPage();
    else if (page === "record") await recordPage();
    else if (page === "settings") await settingsPage();
    else if (page === "runs" && id) await runPage(decodeURIComponent(id));
    else await runsPage();
  } catch (e) {
    show(h("div", {class: "problem"}, e.message));
  }
}

async function loadStatus() {
  state.status = await api("/api/status");
  const s = state.status;
  const pod = document.getElementById("pod");
  let host = "";
  try { host = s.pod_url ? new URL(s.pod_url).host.split(".")[0] : ""; } catch (e) { host = s.pod_url; }
  pod.replaceChildren(h("span", {class: "dot" + (s.ready ? " ok" : "")}),
    s.ready ? `Oracle pod: ${host}` : "Oracle pod not set up");
}

async function loadTests() {
  state.tests = await api("/api/tests");
}

// ------------------------------------------------------------------ Runs page

function targetChoices() {
  const folders = {};
  for (const t of state.tests) if (t.folder) folders[t.folder] = (folders[t.folder] || 0) + 1;
  return [
    h("option", {value: "."}, `All tests (${state.tests.length})`),
    Object.keys(folders).length ? h("optgroup", {label: "A folder of tests"},
      Object.entries(folders).map(([f, n]) => h("option", {value: f}, `${f} (${n} test${n === 1 ? "" : "s"})`))) : null,
    h("optgroup", {label: "One test"},
      state.tests.map((t) => h("option", {value: t.file}, t.title ? `${t.title}  (${t.file})` : t.file))),
  ];
}

function startForm(preselect) {
  const saved = remember("options") || {};
  const d = {...state.status.default_options, ...saved};
  const target = h("select", {id: "target"}, targetChoices());
  target.value = preselect || remember("target") || ".";
  if (!target.value) target.value = ".";
  const shots = h("select", {id: "screenshots"},
    h("option", {value: "every-step"}, "After every step"),
    h("option", {value: "on-failure"}, "Only when a step fails"),
    h("option", {value: "off"}, "No pictures"));
  shots.value = d.screenshots;
  const video = h("select", {id: "video"},
    h("option", {value: "off"}, "No video"),
    h("option", {value: "on-failure"}, "Keep only when a test fails"),
    h("option", {value: "always"}, "Always keep"));
  video.value = d.video;
  const release = h("input", {type: "text", id: "release", value: d.release || "", placeholder: "e.g. 26C"});
  const tester = h("input", {type: "text", id: "tester", value: d.tester || "", placeholder: "Shown as Run by"});
  const headed = h("input", {type: "checkbox", id: "headed", checked: d.headed});
  const ready = state.status.ready;
  const button = h("button", {class: "primary", disabled: !ready || !state.tests.length, onclick: async () => {
    const options = {
      screenshots: shots.value, video: video.value, headed: headed.checked,
      release: release.value.trim(), tester: tester.value.trim(), evidence_doc: true,
    };
    remember("options", options);
    remember("target", target.value);
    button.disabled = true;
    try {
      const run = await api("/api/runs", {target: target.value, options});
      location.hash = `#/runs/${run.id}`;
    } catch (e) {
      toast(e.message);
      button.disabled = false;
    }
  }}, "Start run");

  return h("section", {class: "panel"},
    h("h2", {}, "Start a test run"),
    ready ? null : h("div", {class: "problem"}, "The Oracle pod or its sign-in is not set up yet. See ",
      h("a", {href: "#/settings"}, "Settings"), "."),
    h("div", {class: "form"},
      h("div", {class: "wide"}, h("label", {for: "target"}, "What to test"), target),
      h("div", {}, h("label", {for: "screenshots"}, "Pictures of the screen"), shots,
        h("div", {class: "hint"}, "Pictures go into the Word evidence document.")),
      h("div", {}, h("label", {for: "video"}, "Video"), video,
        h("div", {class: "hint"}, "Videos are saved next to the document, not inside it.")),
      h("div", {}, h("label", {for: "release"}, "Oracle release"), release),
      h("div", {}, h("label", {for: "tester"}, "Your name"), tester),
      h("div", {}, h("label", {class: "check"}, headed, "Show the browser while it runs"))),
    h("div", {class: "actions"}, button,
      h("span", {class: "muted small"}, "Runs wait in line and go one at a time. Nothing is submitted in Oracle unless a test says so.")));
}

function historyTable(runs) {
  if (!runs.length) return h("div", {class: "empty"}, "No runs yet. Start one above.");
  return h("div", {class: "table-wrap"}, h("table", {},
    h("thead", {}, h("tr", {}, h("th", {}, "Started"), h("th", {}, "What was tested"), h("th", {}, "Result"),
      h("th", {class: "hide-sm"}, "Time taken"), h("th", {}, "Evidence"))),
    h("tbody", {}, runs.map((r) => h("tr", {class: "link", onclick: () => { location.hash = `#/runs/${r.id}`; }},
      h("td", {}, when(r.started_at || r.created_at)),
      h("td", {}, targetName(r.target)),
      h("td", {}, pill(r.status)),
      h("td", {class: "hide-sm"}, r.started_at ? took(r.started_at, r.finished_at) : ""),
      h("td", {}, r.summary_url ? h("a", {href: r.summary_url, onclick: (e) => e.stopPropagation()}, "Summary") : ""))))));
}

async function runsPage() {
  await Promise.all([loadStatus(), loadTests()]);
  const runs = await api("/api/runs");
  show(
    h("div", {class: "page-head"}, h("div", {}, h("h1", {}, "Test runs"),
      h("p", {class: "muted"}, "Start a run and follow it step by step. Every finished run has a Word evidence document."))),
    startForm(),
    h("section", {class: "panel"}, h("h2", {}, "Run history"), h("div", {id: "history"}, historyTable(runs))));
  refreshHistory(runs);
}

function refreshHistory(runs) {
  if (!runs.some((r) => r.status === "queued" || r.status === "running")) return;
  schedule(async () => {
    const box = document.getElementById("history");
    if (!box) return;
    const fresh = await api("/api/runs").catch(() => runs);
    box.replaceChildren(historyTable(fresh));
    refreshHistory(fresh);
  }, 2000);
}

// ------------------------------------------------------------------ one run

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
    else if (e.type === "step_start") get(e.test_id).steps[e.index] = {intent: e.intent, status: "running"};
    else if (e.type === "step_end") {
      get(e.test_id).steps[e.index] = {intent: e.intent, status: e.status, error: e.plain_error, detail: e.error};
    }
    else if (e.type === "run_end") get(e.test_id).status = e.status;
  }
  return [...tests.values()];
}

function problem(title, plain, detail) {
  return h("div", {class: "problem"}, h("strong", {}, title), plain ? " " + plain : "",
    detail && detail !== plain ? h("details", {class: "small"}, h("summary", {}, "Details for the test team"), detail) : null);
}

function stepList(t) {
  const items = [];
  const total = Math.max(t.total, t.steps.length);
  const started = t.steps.length;
  for (let i = 0; i < total; i++) {
    if (i >= started) {
      if (started > 0 || t.status !== "waiting") {
        const left = total - started;
        items.push(h("li", {class: "waiting"}, h("span", {class: "n"}, ""), h("span", {class: "ic waiting"}, ""),
          h("span", {}, `${left} more step${left === 1 ? "" : "s"} to go`)));
      }
      break;
    }
    const s = t.steps[i] || {intent: "", status: "waiting"};
    items.push(h("li", {class: s.status},
      h("span", {class: "n"}, `${i + 1}.`),
      h("span", {class: "ic " + s.status, title: LABELS[s.status] || s.status}, ICONS[s.status] || ""),
      h("span", {}, s.intent || (s.status === "waiting" ? "Waiting" : ""),
        s.status === "failed" ? problem("", s.error, s.detail) : null)));
  }
  return h("ol", {class: "steps"}, items);
}

function openButton(path, text) {
  return h("button", {class: "small", onclick: async () => {
    try { await api("/api/open", {path}); } catch (e) { toast(e.message); }
  }}, text);
}

function resultCard(r, live) {
  const steps = live ? stepList(live) : null;
  return h("div", {class: "test-card"},
    h("div", {class: "test-card-head"},
      h("h3", {}, r.test_title || r.test_id),
      h("div", {class: "actions", style: "margin:0"}, pill(r.status),
        h("span", {class: "muted small"}, `${r.steps_passed} of ${r.steps_total} steps passed, ${r.duration}`))),
    r.needs_update ? h("div", {class: "note"},
      "This test passed, but something on the screen was found in a different way than when it was written. Update the test so future runs stay reliable.") : null,
    r.failed_step ? h("div", {},
      problem(`Step ${r.failed_step.number} failed: ${r.failed_step.intent}.`, r.failed_step.error, r.failed_step.detail),
      r.failed_step.picture_url ? h("a", {href: r.failed_step.picture_url, target: "_blank", title: "Open the full picture"},
        h("img", {class: "shot", src: r.failed_step.picture_url, alt: `Screen when step ${r.failed_step.number} failed`})) : null,
      r.failed_step.picture_url ? h("div", {class: "muted small"}, `Screen when step ${r.failed_step.number} failed. Click to open it full size.`) : null) : null,
    steps ? h("details", {}, h("summary", {}, "All steps"), steps) : null,
    h("div", {class: "actions"},
      r.document_url ? h("a", {class: "button small primary", href: r.document_url}, "Evidence document") : null,
      r.videos.map((v, i) => h("a", {class: "button small", href: v, target: "_blank"}, r.videos.length > 1 ? `Video ${i + 1}` : "Video")),
      openButton(r.folder, "Open folder")));
}

async function runPage(id) {
  await loadTests();
  const run = await api(`/api/runs/${encodeURIComponent(id)}`);
  if (location.hash !== `#/runs/${id}`) return; // the page was left while this loaded
  const active = run.status === "queued" || run.status === "running";
  const live = progress(run.events);
  const byId = new Map(live.map((t) => [t.id, t]));
  const openOutput = document.querySelector("details.output-box")?.open || false;

  const cancel = active ? h("button", {class: "danger", onclick: async (ev) => {
    ev.target.disabled = true;
    await api(`/api/runs/${encodeURIComponent(id)}/cancel`, {}).catch((e) => toast(e.message));
    route();
  }}, run.status === "queued" ? "Remove from the line" : "Stop this run") : null;

  let body;
  if (run.results.length) {
    body = run.results.map((r) => resultCard(r, byId.get(r.test_id)));
  } else if (live.length) {
    body = live.map((t) => h("div", {class: "test-card"},
      h("div", {class: "test-card-head"}, h("h3", {}, t.title), pill(t.status)),
      t.status === "waiting" ? null : stepList(t)));
  } else {
    body = h("div", {class: "empty"}, run.status === "queued" ? "Waiting for the run before it to finish." :
      run.status === "running" ? "Opening the browser and signing in…" : "No test results.");
  }

  show(
    h("div", {class: "page-head"},
      h("div", {}, h("a", {href: "#/runs", class: "small"}, "← All runs"), h("h1", {}, targetName(run.target))),
      h("div", {class: "actions", style: "margin:0"}, pill(run.status), cancel,
        run.summary_url ? h("a", {class: "button primary", href: run.summary_url}, "Summary document") : null,
        run.suite_folder ? openButton(run.suite_folder, "Open summary folder") : null)),
    h("section", {class: "panel facts"},
      h("div", {}, h("span", {}, "Started"), when(run.started_at) || "Not yet"),
      h("div", {}, h("span", {}, "Time taken"), run.started_at ? took(run.started_at, run.finished_at) : "–"),
      h("div", {}, h("span", {}, "Pictures"), {"every-step": "After every step", "on-failure": "When a step fails", off: "None"}[run.options.screenshots]),
      h("div", {}, h("span", {}, "Video"), {off: "None", "on-failure": "Kept when a test fails", always: "Always"}[run.options.video]),
      run.options.release ? h("div", {}, h("span", {}, "Oracle release"), run.options.release) : null,
      run.options.tester ? h("div", {}, h("span", {}, "Run by"), run.options.tester) : null),
    run.status === "error" ? h("div", {class: "problem"}, h("strong", {}, "The run could not finish. "), run.error || "") : null,
    body,
    run.output ? h("details", {class: "output-box", open: openOutput}, h("summary", {}, "Messages from the run"),
      h("pre", {class: "output"}, run.output)) : null);

  if (active) schedule(() => runPage(id), 1500);
}

// ------------------------------------------------------------------ Tests page

async function testsPage() {
  await Promise.all([loadStatus(), loadTests()]);
  const rows = [];
  let folder = null;
  for (const t of state.tests) {
    if (t.folder !== folder) {
      folder = t.folder;
      rows.push(h("tr", {class: "folder-row"}, h("td", {colspan: 5}, folder || "Top folder")));
    }
    rows.push(h("tr", {},
      h("td", {}, t.title || t.file, h("div", {class: "muted small"}, t.file),
        t.problem ? h("div", {class: "problem small"}, t.problem) : null),
      h("td", {class: "hide-sm"}, t.module || ""),
      h("td", {class: "hide-sm"}, t.steps ?? ""),
      h("td", {}, t.last_run ? h("a", {href: `#/runs/${t.last_run.id}`}, pill(t.last_run.status)) : h("span", {class: "muted small"}, "Never run")),
      h("td", {}, h("button", {class: "small", disabled: !state.status.ready || Boolean(t.problem), onclick: async (ev) => {
        ev.target.disabled = true;
        const options = {...state.status.default_options, ...(remember("options") || {})};
        try {
          const run = await api("/api/runs", {target: t.file, options});
          location.hash = `#/runs/${run.id}`;
        } catch (e) { toast(e.message); ev.target.disabled = false; }
      }}, "Run"))));
  }
  show(
    h("div", {class: "page-head"}, h("div", {}, h("h1", {}, "Tests"),
      h("p", {class: "muted"}, `${state.tests.length} test file(s) in `, h("code", {}, state.status.tests_folder))),
      h("a", {class: "button primary", href: "#/record"}, "Record a new test")),
    h("section", {class: "panel"}, state.tests.length ? h("div", {class: "table-wrap"}, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Test"), h("th", {class: "hide-sm"}, "Module"), h("th", {class: "hide-sm"}, "Steps"),
        h("th", {}, "Last result"), h("th", {}, ""))),
      h("tbody", {}, rows))) : h("div", {class: "empty"}, "No test files yet. Record one to get started.")));
}

// ------------------------------------------------------------------ Record page

async function recordPage() {
  await loadStatus();
  const rec = await api("/api/recording");
  if (location.hash !== "#/record") return;
  const busy = rec.status === "recording" || rec.status === "saving";

  let top = null;
  if (rec.status === "recording") {
    top = h("div", {class: "info"},
      h("h2", {}, `Recording "${rec.title}"`),
      h("p", {}, "A browser window has opened and signed in to Oracle for you. Do the steps of the test in that window."),
      h("p", {}, "To record something that must be true, such as a value on the screen, use ", h("strong", {}, "Add check"),
        " in the small toolbar at the top of that window."),
      h("div", {class: "actions"}, h("button", {class: "primary", onclick: async () => {
        await api("/api/recording/stop", {}).catch((e) => toast(e.message));
        recordPage();
      }}, "Stop recording and save"),
      h("span", {class: "muted small"}, "You can also click Stop recording in the browser window.")));
  } else if (rec.status === "saving") {
    top = h("div", {class: "info"}, h("h2", {}, "Saving the recording…"));
  } else if (rec.status === "saved") {
    top = h("div", {class: "info"}, h("h2", {}, "Recording saved"),
      h("p", {}, rec.message || "", " The test is in ", h("code", {}, rec.file), "."),
      h("div", {class: "actions"}, h("button", {class: "primary", onclick: async () => {
        try {
          const run = await api("/api/runs", {target: rec.file, options: {...state.status.default_options, ...(remember("options") || {})}});
          location.hash = `#/runs/${run.id}`;
        } catch (e) { toast(e.message); }
      }}, "Run it now"), h("a", {href: "#/tests"}, "See all tests")));
  } else if (rec.status === "error") {
    top = h("div", {class: "problem"}, h("strong", {}, "The recording was not saved. "), rec.message || "");
  }

  const field = (id, label, hint, placeholder, value) => h("div", {},
    h("label", {for: "r-" + id}, label),
    h("input", {type: "text", id: "r-" + id, placeholder, value: value || ""}),
    hint ? h("div", {class: "hint"}, hint) : null);
  const saved = remember("record") || {};

  const form = h("section", {class: "panel"},
    h("h2", {}, "Record a new test"),
    h("p", {class: "muted"}, "Quartermaster opens Oracle in a browser and writes down each click and entry as a test step. Sign-in is done for you and is not recorded."),
    h("div", {class: "form"},
      field("title", "Test name", "What the test checks, in plain words.", "View a worker's details"),
      field("id", "Test id", "Short and unique. Lower-case, no spaces.", "hcm.view-worker"),
      field("module", "Module", null, "HCM", saved.module),
      field("product", "Product", null, "Global Human Resources", saved.product),
      field("persona", "Role (optional)", "The job role the test runs as.", "HR Specialist", saved.persona),
      field("file", "Save as (optional)", "Inside the tests folder. Default: recorded/<test id>.yaml", "recorded/view_worker.yaml")),
    h("div", {class: "actions"}, h("button", {class: "primary", disabled: busy || !state.status.ready, onclick: async (ev) => {
      const val = (k) => document.getElementById("r-" + k).value.trim();
      const request = {title: val("title"), id: val("id"), module: val("module"), product: val("product"),
        persona: val("persona"), file: val("file")};
      remember("record", {module: request.module, product: request.product, persona: request.persona});
      ev.target.disabled = true;
      try { await api("/api/recording", request); } catch (e) { toast(e.message); ev.target.disabled = false; return; }
      recordPage();
    }}, "Start recording"),
    state.status.ready ? null : h("span", {class: "muted small"}, "Set up the Oracle pod first (see Settings).")));

  show(
    h("div", {class: "page-head"}, h("div", {}, h("h1", {}, "Record"),
      h("p", {class: "muted"}, "Create a test by doing the steps yourself, once."))),
    top, busy ? null : form);
  if (busy) schedule(recordPage, 1500);
}

// ------------------------------------------------------------------ Settings page

async function settingsPage() {
  await loadStatus();
  const s = state.status;
  const row = (name, value, ok) => h("tr", {}, h("td", {}, name), h("td", {}, value),
    h("td", {}, ok === undefined ? "" : pill(ok ? "passed" : "failed")));
  show(
    h("div", {class: "page-head"}, h("div", {}, h("h1", {}, "Settings"),
      h("p", {class: "muted"}, "What this Quartermaster uses. Passwords are never shown."))),
    h("section", {class: "panel"}, h("h2", {}, "Oracle pod"),
      h("table", {}, h("tbody", {},
        row("Pod address (QM_FUSION_URL)", s.pod_url || "Not set", Boolean(s.pod_url)),
        row("User name (QM_FUSION_USER)", s.user || "Not set", Boolean(s.user)),
        row("Password (QM_FUSION_PASSWORD)", s.password_set ? "Set" : "Not set", s.password_set))),
      h("p", {class: "muted small", style: "margin-top:12px"},
        "These come from environment variables on this computer. To change them, set the variables, close the Quartermaster window and run ",
        h("code", {}, "qm serve"), " again. Use a test or development pod only, never production.")),
    h("section", {class: "panel"}, h("h2", {}, "Folders"),
      h("table", {}, h("tbody", {},
        row("Tests", s.tests_folder), row("Evidence (documents, pictures, videos)", s.evidence_folder))),
      h("div", {class: "actions"}, openButton(".", "Open the evidence folder"))));
}

// ------------------------------------------------------------------ start

window.addEventListener("hashchange", route);
route();
