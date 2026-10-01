// Doing a manual scenario by hand: the scenario's steps on one side, the signed-in browser on the
// other. The tester marks each step Pass or Fail; Quartermaster takes a picture each time and
// remembers the clicks, so next time the scenario plays by itself.
import {api, button, callout, card, emptyState, h, icon, statusBadge, toast} from "./ui.js";
import {loadCommon, runLink, schedule, state} from "./state.js";
import {show} from "./app.js";

let ws = null;

export async function manualRunPage() {
  if (!state.status || !ws) await loadCommon();
  const rec = await api("/api/recording");
  if (state.page !== "manual-run") return;
  if (rec.mode !== "manual") {
    ws = null;
    if (rec.status === "recording" || rec.status === "saving") { location.hash = "#/record"; return; }
    show([{label: "Tests", href: "#/tests?view=manual"}, {label: "Run by hand"}],
      h("div", {class: "card"}, emptyState({ic: "file", title: "No scenario is being done by hand",
        text: "Open Manual scenarios and click Run on a scenario.",
        actions: button("Manual scenarios", {kind: "primary", size: "sm", href: "#/tests?view=manual"})})));
    return;
  }
  const crumbs = [{label: "Tests", href: "#/tests?view=manual"}, {label: rec.title}];
  if (rec.status === "recording" || rec.status === "saving") {
    if (!ws || !ws.el.isConnected) { ws = workspace(rec); show(crumbs, ws.el); }
    ws.update(rec);
    schedule(manualRunPage, 1000);
    return;
  }
  ws = null;
  show(crumbs, outcome(rec));
  if (rec.status === "saved" && !rec.run_id) schedule(manualRunPage, 1000); // the run is being added to the history
}

function outcome(rec) {
  if (rec.status === "error") {
    return h("div", {class: "stack"},
      h("div", {class: "page-head"}, h("div", {}, h("h1", {}, rec.title), h("p", {class: "lead"}, "Not saved"))),
      callout("danger", "Nothing was saved.", rec.message || ""),
      h("div", {class: "row"}, button("Back to manual scenarios", {href: "#/tests?view=manual"})));
  }
  const passed = rec.result === "passed";
  return h("div", {class: "stack"},
    h("div", {class: "page-head"}, h("div", {}, h("h1", {}, rec.title),
      h("p", {class: "lead"}, `Done by hand${rec.tester ? ` by ${rec.tester}` : ""}${rec.release ? ` on ${rec.release}` : ""}.`))),
    card({body: h("div", {class: "stack", style: "gap:14px"},
      h("div", {class: "row"}, statusBadge(passed ? "passed" : "failed"),
        h("strong", {}, passed ? "Every step passed." : "At least one step failed or was not checked.")),
      rec.automated
        ? callout("info", "Next time it plays by itself.", "Quartermaster remembered your clicks. Click Run on this scenario again and it runs without you, with the same evidence.")
        : callout("warning", "It cannot play by itself yet.", rec.message || "No clicks were recorded."),
      h("div", {class: "row"},
        rec.document_url ? button("Evidence document", {kind: "primary", ic: "download", href: rec.document_url}) : null,
        rec.run_id ? button("Open the run", {ic: "runs", href: runLink(rec.run_id)}) : h("span", {class: "meta"}, "Adding it to the run history…"),
        button("Back to manual scenarios", {href: "#/tests?view=manual"})))}));
}

function workspace(rec) {
  const list = h("ol", {class: "guide", "aria-label": "Steps"});
  const message = h("div", {class: "meta", role: "status", "aria-live": "polite", style: "min-height:18px"});
  const progress = h("span", {class: "meta"});
  const send = async (command, text) => {
    try { await api(`/api/recording/${command}`, text === undefined ? {} : {text}); manualRunPage(); }
    catch (err) { toast(err.message); }
  };
  let steps = [];
  const checkBtn = button("Add check", {ic: "target", title: "The next click in the browser checks a value instead of doing an action",
    onClick: () => send("check")});
  const finishBtn = button("Finish", {kind: "primary", ic: "check", onClick: () => {
    const open = steps.filter((st) => !st.status).length;
    if (open && !confirm(`${open} step${open === 1 ? " is" : "s are"} not marked yet and will count as not checked, so the run will not pass. Finish anyway?`)) return;
    send("stop");
  }});

  const el = h("div", {},
    h("div", {class: "page-head"},
      h("div", {}, h("h1", {}, rec.title),
        h("p", {class: "lead"}, `${rec.ref} · ${rec.workbook}${rec.release ? ` · Release ${rec.release}` : ""}`)),
      h("div", {class: "row"}, checkBtn, finishBtn)),
    callout("info", "Do each step in the browser window that opened (it is already signed in), then mark it here.",
      "Quartermaster takes a picture of the screen when you mark a step, and remembers your clicks so the scenario can play by itself next time. Add check, then click a value on the screen, proves a page shows what it should."),
    h("section", {class: "card section"},
      h("div", {class: "card-head"}, h("div", {class: "grow"}, h("h3", {}, "Steps"), message), progress),
      h("div", {class: "card-body"}, list)));

  const row = (st, current) => {
    const note = h("input", {class: "input", placeholder: "What went wrong?", "aria-label": `What went wrong at step ${st.number}`});
    const failBox = h("div", {class: "row", style: "gap:8px;margin-top:8px;display:none"}, note,
      button("Mark failed", {size: "sm", kind: "danger", onClick: () => send("result", `${st.number} fail ${note.value.trim()}`)}),
      button("Cancel", {size: "sm", kind: "ghost", onClick: () => { failBox.style.display = "none"; }}));
    note.onkeydown = (e) => { if (e.key === "Enter") send("result", `${st.number} fail ${note.value.trim()}`); };
    const marks = h("div", {class: "row", style: "gap:6px;flex-wrap:nowrap"},
      button("Pass", {size: "sm", kind: st.status === "passed" ? "primary" : "", ic: "check",
        title: `Step ${st.number} worked`, onClick: () => send("result", `${st.number} pass`)}),
      button("Fail", {size: "sm", ic: "x", title: `Step ${st.number} did not work`,
        onClick: () => { failBox.style.display = "flex"; note.focus(); }}));
    return h("li", {class: `guide-step${current ? " current" : ""}${st.status ? ` is-${st.status}` : ""}`, "aria-current": current ? "step" : null},
      h("span", {class: `node ${st.status === "passed" ? "success" : st.status === "failed" ? "danger" : current ? "info" : ""}`},
        st.status === "passed" ? icon("check") : st.status === "failed" ? icon("x") : st.number),
      h("div", {style: "min-width:0", class: "grow"},
        st.case_name && st.case !== st.case_name ? h("div", {class: "caption"}, `${st.case} · ${st.case_name}`) : null,
        h("div", {style: "font-weight:500;white-space:pre-line"}, st.action),
        st.expected ? h("div", {class: "meta", style: "white-space:pre-line"}, "Expected: ", st.expected) : null,
        st.status === "failed" && st.note ? h("div", {class: "meta", style: "color:var(--danger)"}, "Failed: ", st.note) : null,
        st.picture_note ? h("div", {class: "meta"}, st.picture_note) : null,
        failBox),
      h("div", {class: "stack", style: "gap:6px;align-items:flex-end"},
        st.picture_url ? h("a", {href: st.picture_url, target: "_blank", rel: "noopener", title: `Picture of step ${st.number}`},
          h("img", {src: st.picture_url, alt: `Screen at step ${st.number}`, class: "guide-shot"})) : null,
        marks));
  };

  const update = (r) => {
    const feed = r.feed;
    if (r.status === "saving") {
      [checkBtn, finishBtn].forEach((b) => { b.disabled = true; });
      message.textContent = "Saving the evidence and the steps you clicked…";
      return;
    }
    steps = feed?.guide || [];
    message.textContent = !feed ? "Opening the browser and signing in to Oracle Fusion…" : feed.checking ? "Click the value to check in the browser window." : feed.message || "";
    checkBtn.setAttribute("aria-pressed", String(Boolean(feed?.checking)));
    checkBtn.disabled = !feed;
    finishBtn.disabled = !feed;
    const done = steps.filter((st) => st.status).length;
    progress.textContent = steps.length ? `${done} of ${steps.length} marked` : "";
    const sig = JSON.stringify(steps);
    if (list.dataset.sig === sig) return;
    list.dataset.sig = sig;
    const current = steps.findIndex((st) => !st.status);
    list.replaceChildren(...(steps.length ? steps.map((st, i) => row(st, i === current)) : [h("li", {}, emptyState({ic: "loader", title: "Opening the browser",
      text: "It signs in to Oracle Fusion for you."}))]));
    list.querySelector(".current")?.scrollIntoView({block: "nearest", behavior: "smooth"});
  };
  return {el, update};
}
