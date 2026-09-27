// Needs attention: the failure and maintenance workspace.
import {api, badge, button, chips, clock, disclose, emptyState, h, icon, toast, when} from "./ui.js";
import {openRunDrawer, openViewer} from "./components.js";
import {loadCommon, runLink, state, testLink} from "./state.js";
import {show} from "./app.js";

const ORDER = ["assertion", "missing_element", "timeout", "authentication", "failure", "could_not_run", "ui_change", "unreadable"];
const LOOK = {
  assertion: {ic: "x", tone: "danger", short: "Check did not match"},
  missing_element: {ic: "target", tone: "danger", short: "Item not found"},
  timeout: {ic: "clock", tone: "danger", short: "Screen did not respond"},
  authentication: {ic: "lock", tone: "danger", short: "Sign-in problem"},
  failure: {ic: "x", tone: "danger", short: "Failed"},
  could_not_run: {ic: "attention", tone: "danger", short: "Could not run"},
  ui_change: {ic: "wrench", tone: "warning", short: "Oracle screen changed"},
  unreadable: {ic: "file", tone: "danger", short: "Unreadable file"},
};
let current = "all";

export async function attentionPage() {
  await loadCommon();
  if (state.page !== "attention") return;
  const a = state.attention;
  const list = h("div", {class: "stack", style: "gap:12px"});
  const draw = () => {
    const items = a.items.filter((i) => current === "all" || i.category === current)
      .sort((x, y) => ORDER.indexOf(x.category) - ORDER.indexOf(y.category));
    list.replaceChildren(...items.map(item));
  };
  draw();
  show([{label: "Needs attention"}],
    h("div", {class: "page-head"},
      h("div", {}, h("h1", {}, "Needs attention"),
        h("p", {class: "lead"}, "Failures to look into, Oracle screen changes to accept, and anything that stopped a run.")),
      h("span", {class: "meta"}, `Last checked ${clock(a.checked_at)}`)),
    a.count ? [
      h("div", {class: "toolbar"}, chips([["all", "All", a.count],
        ...ORDER.filter((k) => a.counts[k]).map((k) => [k, a.categories[k], a.counts[k]])], current, (v) => { current = v; draw(); }, "Kind")),
      list,
    ] : h("div", {class: "card"}, emptyState({ic: "check", tone: "success", title: "All clear",
      text: `No tests currently need attention. Last checked ${clock(a.checked_at)}.`,
      actions: button("Run all tests", {size: "sm", ic: "runs", disabled: !state.status.ready, onClick: () => openRunDrawer(".")})})));
}

function item(i) {
  const look = LOOK[i.category] || LOOK.failure;
  const head = h("div", {class: "row", style: "align-items:flex-start;flex-wrap:nowrap;gap:12px"},
    h("span", {class: `icon-tile tone-${look.tone}`}, icon(look.ic)),
    h("div", {class: "grow"},
      h("div", {class: "row", style: "gap:8px"},
        i.file && i.category !== "unreadable" && i.test_id ? h("a", {href: testLink(i.file), style: "color:inherit"}, h("h3", {}, i.title)) : h("h3", {}, i.title),
        badge(look.short, look.tone)),
      h("div", {class: "meta"}, [i.module, i.process].filter(Boolean).join(" › ") || (i.file ? i.file : ""))),
    h("div", {class: "row"}, actions(i)));

  let body = null;
  if (i.category === "ui_change") {
    body = h("div", {class: "stack", style: "gap:8px"},
      h("div", {}, `Step ${i.step}: ${i.intent}`),
      h("div", {class: "compare"},
        h("div", {}, h("span", {class: "caption"}, "Written to find"), i.old_text),
        h("div", {}, h("span", {class: "caption"}, "Found last time by"), i.new_text)),
      h("p", {class: "meta"}, "The test passed by trying its second way. Accepting makes that the first way, so it keeps passing after the quarterly update. A copy of the old file is kept."));
  } else if (i.category === "unreadable") {
    body = h("pre", {class: "block"}, i.error);
  } else if (i.step) {
    body = h("div", {class: "stack", style: "gap:8px"},
      h("div", {}, h("strong", {}, `Failed at step ${i.step}: `), i.intent),
      h("div", {}, i.error),
      i.compare ? h("div", {class: "compare"},
        h("div", {}, h("span", {class: "caption"}, "Expected"), i.compare.expected || "(empty)"),
        h("div", {}, h("span", {class: "caption"}, "Observed"), i.compare.observed || "(empty)")) : null,
      i.detail && i.detail !== i.error ? disclose("Technical details", h("pre", {class: "block"}, i.detail)) : null);
  } else {
    body = h("div", {class: "stack", style: "gap:8px"}, h("div", {}, i.error),
      i.category === "authentication" ? h("p", {class: "meta"}, "Check the user name and password on this computer (Settings), then run it again.") : null,
      i.detail && i.detail !== i.error ? disclose("Messages from the run", h("pre", {class: "block"}, i.detail)) : null);
  }

  const facts = i.category === "unreadable" ? null : h("div", {class: "facts", style: "margin-top:4px"},
    i.test_id ? fact("Last successful release", i.last_good_release ? h("span", {class: "release"}, i.last_good_release)
      : i.last_good_at ? "Not recorded" : "Never passed") : null,
    fact("Current release", i.current_release ? h("span", {class: "release"}, i.current_release) : h("a", {href: "#/settings"}, "Not set")),
    i.run_release !== undefined ? fact("Release of this run", i.run_release ? h("span", {class: "release"}, i.run_release) : "Not recorded") : null,
    i.at ? fact(i.category === "ui_change" ? "Found" : "Happened", when(i.at)) : null);

  const evidence = (i.picture_url || i.document_url) ? h("div", {class: "row", style: "gap:12px"},
    i.picture_url ? h("img", {class: "thumb", src: i.picture_url, alt: `Screen when step ${i.step} failed`, style: "width:120px;height:75px",
      onclick: () => openViewer([{src: i.picture_url, caption: `Step ${i.step}: ${i.intent}`, sub: i.title}])}) : null,
    i.document_url ? button("Evidence document", {size: "sm", ic: "file", href: i.document_url}) : null) : null;

  return h("article", {class: "card", "aria-label": `${look.short}: ${i.title}`},
    h("div", {class: "card-body stack", style: "gap:12px"}, head, body, evidence, facts));
}

function actions(i) {
  const out = [];
  if (i.category === "ui_change") {
    out.push(button("Accept update", {kind: "primary", size: "sm", ic: "check", onClick: async (e) => {
      e.currentTarget.disabled = true;
      try {
        await api("/api/test/accept-update", {file: i.file, step_index: i.step_index, new: i.new});
        toast("Test updated. A copy of the old file was kept.");
        attentionPage();
      } catch (err) { toast(err.message); e.currentTarget.disabled = false; }
    }}));
  }
  if (i.run_id) out.push(button("See the run", {size: "sm", href: runLink(i.run_id)}));
  if (i.category === "authentication") out.push(button("Settings", {size: "sm", href: "#/settings"}));
  if (i.file && i.category !== "ui_change" && i.category !== "unreadable") {
    out.push(button("Run again", {size: "sm", kind: i.category === "ui_change" ? "" : "primary", ic: "runs", disabled: !state.status.ready, onClick: () => openRunDrawer(i.file)}));
  }
  if (i.category === "unreadable") out.push(button("Open the test", {size: "sm", href: testLink(i.file)}));
  return out;
}

function fact(k, v) {
  return h("div", {}, h("div", {class: "k"}, k), h("div", {class: "v"}, v));
}

