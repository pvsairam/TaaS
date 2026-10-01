// Manual scenarios: test scripts imported from Excel, listed next to the automated tests and
// matched to release features. They cannot run by themselves; they tell testers what to do by hand.
import {
  api, badge, button, callout, chips, drawer, emptyState, h, icon, input, plural, popover, statusBadge, table, toast, when,
} from "./ui.js";
import {loadCommon, state} from "./state.js";
import {show} from "./app.js";

const filters = {q: "", module: "all"};

export function manualLink(id) {
  return "#/tests?view=manual&open=" + encodeURIComponent(id);
}

// The Automated / Manual switch at the top of the Tests page.
export function testsViewSwitch(current, counts) {
  return chips([["automated", "Automated", counts.automated], ["manual", "Manual scenarios", counts.manual]], current,
    (v) => { location.hash = v === "manual" ? "#/tests?view=manual" : "#/tests"; }, "Kind of test");
}

export async function manualPage() {
  const [, data] = await Promise.all([loadCommon(), api("/api/manual")]);
  if (state.page !== "tests" || state.query.view !== "manual") return;
  const all = data.scenarios;
  const modules = [...new Set(all.map((s) => s.module).filter(Boolean))].sort();
  if (!modules.includes(filters.module)) filters.module = "all";
  const body = h("div", {});

  const draw = () => {
    const q = filters.q.toLowerCase();
    const shown = all.filter((s) => (filters.module === "all" || s.module === filters.module) &&
      (!q || [s.title, s.ref, s.product, s.module, s.file, s.description].join(" ").toLowerCase().includes(q)));
    body.replaceChildren(shown.length ? table({
      caption: "Manual scenarios",
      rows: shown,
      onRow: (s) => openScenario(s.id),
      columns: [
        {label: "Scenario", render: (s) => [h("div", {class: "primary-cell"}, s.title), h("div", {class: "sub"}, `${s.ref} · ${s.file}`)]},
        {label: "Module", render: (s) => [h("div", {}, s.module), h("div", {class: "sub"}, s.product)]},
        {label: "Cases", cls: "num", render: (s) => s.case_count},
        {label: "Steps", cls: "num", render: (s) => s.step_count},
        // Only what someone typed in the workbook's Pass / Fail column; Quartermaster has not run these.
        {label: "Result in workbook", render: (s) => s.status
          ? h("span", {title: `Typed in the workbook${s.tester ? ` by ${s.tester}` : ""}. Not a Quartermaster run.`},
            statusBadge(s.status, s.status === "passed" ? "Pass in workbook" : "Fail in workbook"))
          : h("span", {class: "muted"}, "None")},
        {label: "Notes", render: (s) => h("div", {class: "row", style: "gap:4px"},
          s.blank_data ? badge("Test data missing", "warning") : null,
          s.releases?.length ? badge(`Workbook: ${s.releases.join(", ")}`, "neutral") : null)},
      ],
    }) : emptyState(all.length
      ? {ic: "search", title: "No scenarios match", text: "Try another search or module."}
      : {ic: "file", tone: "primary", title: "No manual scripts yet",
        text: "Import your Excel test scripts (a Test Scenarios and Test Cases workbook, or a list of actions with reference numbers). They are read on this computer and matched to Oracle release features.",
        actions: button("Import manual scripts", {kind: "primary", size: "sm", ic: "download", onClick: () => openManualImport()})}));
  };
  draw();

  const filesBtn = data.files.length ? button(`Imported files: ${data.files.length}`, {ic: "folder", attrs: {"aria-haspopup": "dialog"},
    onClick: (e) => popover(e.currentTarget, (close) => h("div", {class: "pop-body", style: "gap:2px;max-width:440px;max-height:60vh;overflow:auto"},
      h("div", {class: "caption", style: "padding:0 8px 6px"}, "IMPORTED WORKBOOKS"),
      data.files.map((f) => h("div", {class: "row", style: "flex-wrap:nowrap;gap:8px;padding:6px 8px;align-items:flex-start"},
        h("div", {class: "grow", style: "min-width:0"}, h("div", {class: "ellipsis", style: "font-weight:500"}, f.file),
          h("div", {class: "meta"}, `${f.module} · ${f.product} · ${plural(f.scenarios, "scenario")}${f.imported_at ? ` · ${when(f.imported_at)}` : ""}`),
          f.warnings.length ? h("div", {class: "meta", style: "color:var(--warning)"}, plural(f.warnings.length, "note")) : null),
        button("Remove", {size: "sm", kind: "ghost", title: `Forget ${f.file}`, onClick: async () => {
          if (!confirm(`Forget ${f.file}? The Excel file itself is not touched.`)) return;
          try { await api("/api/manual/remove", {key: f.key}); toast(`Removed ${f.file}.`); close(); manualPage(); } catch (err) { toast(err.message); }
        }}))),
      h("div", {class: "hint", style: "padding:6px 8px 0"}, "Import a workbook again to replace it.")))}) : null;

  const totals = {cases: all.reduce((a, s) => a + s.case_count, 0), steps: all.reduce((a, s) => a + s.step_count, 0)};
  show([{label: "Tests", href: "#/tests"}, {label: "Manual scenarios"}],
    h("div", {class: "page-head"},
      h("div", {}, h("h1", {}, "Tests"),
        h("p", {class: "lead"}, all.length
          ? `${plural(all.length, "manual scenario")}, ${plural(totals.cases, "test case")} and ${plural(totals.steps, "step")} from ${plural(data.files.length, "workbook")}.`
          : "Manual test scripts imported from Excel.")),
      h("div", {class: "row"}, filesBtn, button("Import manual scripts", {kind: all.length ? "" : "primary", ic: "download", onClick: () => openManualImport()}))),
    h("div", {class: "toolbar"}, testsViewSwitch("manual", {automated: state.tests.length, manual: all.length})),
    all.length ? h("div", {class: "toolbar"},
      h("div", {class: "search"}, icon("search"), input({type: "search", value: filters.q, placeholder: "Search scenario, product or file",
        "aria-label": "Search manual scenarios", oninput: (e) => { filters.q = e.target.value; draw(); }})),
      modules.length > 1 ? chips([["all", "All modules"], ...modules.map((m) => [m, m, all.filter((s) => s.module === m).length])],
        filters.module, (v) => { filters.module = v; draw(); }, "Module") : null) : null,
    h("div", {class: "card"}, body));

  if (state.query.open) openScenario(state.query.open);
}

// ------------------------------------------------------------------ one scenario

export async function openScenario(id) {
  let s;
  try { s = await api("/api/manual/scenario?id=" + encodeURIComponent(id)); } catch (e) { toast(e.message); return; }
  const facts = [
    ["Product", `${s.module} · ${s.product}`], ["Workbook", s.file], ["Scenario", [s.use_case, s.ref].filter(Boolean).join(" · ")],
    s.tester ? ["Tester in workbook", s.tester] : null, s.minutes ? ["Time in workbook", `${s.minutes} min`] : null,
    s.releases?.length ? ["Workbook says tested in", s.releases.join(", ")] : null,
  ].filter(Boolean);
  drawer({
    title: s.title,
    sub: `${plural(s.case_count, "test case")} · ${plural(s.step_count, "step")} · manual: follow the steps on the pod`,
    body: () => [
      s.status ? callout("info", `The workbook says ${s.status === "passed" ? "Pass" : "Fail"}.`,
        `Someone typed this in its Pass / Fail column${s.tester ? ` (tester ${s.tester})` : ""}${s.releases?.length ? `, for ${s.releases.join(" and ")}` : ""}. Quartermaster has not run this scenario.`) : null,
      h("dl", {class: "kv"}, facts.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
      s.description ? h("p", {}, s.description) : null,
      s.blank_data ? callout("warning", "Test data missing.", "Some steps say <> where a value should be, such as a user or supplier. Fill these in before testing.") : null,
      s.fields?.length ? h("div", {}, h("div", {class: "caption", style: "margin-bottom:6px"}, "FIELDS TO CHECK"),
        h("ul", {style: "margin:0;padding-left:18px"}, s.fields.map((f) => h("li", {}, f)))) : null,
      ...s.cases.map((c) => h("section", {class: "card", style: "padding:14px 16px"},
        h("div", {class: "row", style: "gap:8px;margin-bottom:4px"}, h("span", {class: "tag"}, c.id), h("strong", {}, c.name)),
        c.description && c.description !== c.name ? h("p", {class: "meta", style: "margin:0 0 8px"}, c.description) : null,
        c.precondition ? h("p", {class: "meta", style: "margin:0 0 8px;white-space:pre-line"}, h("strong", {}, "Before you start: "), c.precondition) : null,
        c.steps.length ? h("ol", {class: "stack", style: "gap:8px;margin:0;padding-left:20px"}, c.steps.map((st) => h("li", {},
          h("div", {style: "white-space:pre-line"}, st.action),
          st.expected ? h("div", {class: "meta", style: "white-space:pre-line"}, "Expected: ", st.expected) : null))) :
          h("p", {class: "muted", style: "margin:0"}, "No steps written."))),
    ],
  });
}

// ------------------------------------------------------------------ import

export function openManualImport() {
  let picked = [];
  let preview = null;
  const fileInput = h("input", {type: "file", class: "input", multiple: true, accept: ".xlsx,.xlsm", "aria-describedby": "mi-hint"});
  const result = h("div", {class: "stack", "aria-live": "polite"});
  const saveBtn = button("Save", {kind: "primary", ic: "check", disabled: true});
  const overrides = {}; // file name -> {module, product} typed by the reader

  const read = (file) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve({name: file.name, content: String(r.result).split(",", 2)[1] || ""});
    r.onerror = () => reject(new Error(`${file.name} could not be read`));
    r.readAsDataURL(file);
  });
  const payload = () => picked.map((f) => ({...f, ...(overrides[f.name] || {})}));

  async function check() {
    saveBtn.disabled = true;
    result.replaceChildren(h("div", {class: "skel", style: "height:120px"}));
    try {
      preview = await api("/api/manual/import", {files: payload()});
      drawPreview();
    } catch (err) {
      result.replaceChildren(callout("danger", "These files cannot be used.", err.message));
    }
  }

  function drawPreview() {
    const ok = preview.files.filter((f) => !f.problem);
    const sum = (k) => ok.reduce((a, f) => a + f[k], 0);
    result.replaceChildren(
      ok.length ? callout("info", `${plural(sum("scenarios"), "scenario")}, ${plural(sum("cases"), "test case")} and ${plural(sum("steps"), "step")} found.`,
        `In ${plural(ok.length, "workbook")}. Check the module and product of each; they decide which release features a scenario is matched to.`) : null,
      ...preview.files.map((f) => f.problem
        ? callout("danger", `${f.file}:`, f.problem)
        : h("section", {class: "card", style: "padding:12px 14px"},
          h("div", {class: "row", style: "gap:8px;flex-wrap:nowrap"}, icon("file"), h("strong", {class: "ellipsis grow"}, f.file),
            f.replaces ? badge("Replaces the earlier import", "neutral") : null),
          h("div", {class: "meta", style: "margin:4px 0 8px"},
            `${plural(f.scenarios, "scenario")} · ${plural(f.cases, "test case")} · ${plural(f.steps, "step")}`,
            f.blank_data ? ` · ${f.blank_data} with test data missing` : ""),
          h("div", {class: "fields"},
            fieldInput("Module", f, "module", "e.g. HCM"), fieldInput("Product", f, "product", "e.g. Payables")),
          f.warnings.length ? h("ul", {style: "margin:8px 0 0;padding-left:18px"}, f.warnings.map((w) => h("li", {class: "meta", style: "color:var(--warning)"}, w))) : null)),
    );
    drawSaveState();
  }

  function fieldInput(label, f, key, placeholder) {
    const value = overrides[f.file]?.[key] ?? f[key];
    const el = input({value, placeholder, "aria-label": `${label} of ${f.file}`, oninput: (e) => {
      overrides[f.file] = {...(overrides[f.file] || {}), [key]: e.target.value.trim()};
      drawSaveState();
    }});
    return h("label", {}, h("span", {class: "label"}, label), el);
  }

  function drawSaveState() {
    const ok = preview.files.filter((f) => !f.problem);
    const ready = ok.filter((f) => (overrides[f.file]?.product ?? f.product) && (overrides[f.file]?.module ?? f.module));
    saveBtn.disabled = !ready.length;
    saveBtn.querySelector("span").textContent = ready.length ? `Save ${plural(ready.length, "workbook")}` : "Save";
  }

  fileInput.onchange = async () => {
    preview = null;
    saveBtn.disabled = true;
    try { picked = await Promise.all([...fileInput.files].map(read)); } catch (err) { result.replaceChildren(callout("danger", err.message, null)); return; }
    if (picked.length) check(); else result.replaceChildren();
  };

  drawer({
    title: "Import manual scripts",
    sub: "Excel test scripts, so release impact can point to the manual scenario that covers a feature.",
    body: (close) => {
      saveBtn.onclick = async () => {
        saveBtn.disabled = true;
        try {
          const saved = await api("/api/manual/import", {files: payload(), save: true});
          const skipped = saved.files.length - saved.saved;
          toast(`Saved ${plural(saved.saved, "workbook")}.${skipped ? ` ${skipped} left out (see the notes).` : ""}`);
          close();
          if (location.hash.startsWith("#/tests?view=manual")) manualPage(); else location.hash = "#/tests?view=manual";
        } catch (err) { toast(err.message); saveBtn.disabled = false; }
      };
      return [
        h("div", {}, h("div", {class: "label"}, "Workbooks"), fileInput,
          h("div", {class: "hint", id: "mi-hint"}, "Choose one or more .xlsx files. Two layouts are read: a Test Scenarios sheet with a Test Cases sheet (Scenario ID, Test case ID, Test step description, Expected result), or a list of actions with Reference Number and Primary Navigation.")),
        callout("info", "Nothing is saved until you choose Save.", "The workbooks are read on this computer and are not changed. A summary of each is kept in the Quartermaster data folder."),
        result,
      ];
    },
    foot: (close) => [h("span", {class: "grow"}), button("Cancel", {onClick: close}), saveBtn],
  });
}
