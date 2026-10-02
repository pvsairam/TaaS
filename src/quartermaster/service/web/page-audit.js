// Audit log: who changed what in Quartermaster, and when. Read only; lines are never changed.
import {api, button, emptyState, h, icon, input, table, when} from "./ui.js";
import {loadCommon, runLink, state} from "./state.js";
import {show} from "./app.js";

let query = "";

export async function auditPage() {
  const [, data] = await Promise.all([loadCommon(), api("/api/audit")]);
  if (state.page !== "audit") return;
  const all = data.entries;
  const text = (e) => [e.who, e.action, e.subject, ...Object.entries(e.details || {}).map(([k, v]) => `${k} ${v}`)].join(" ").toLowerCase();
  const body = h("div", {});
  const draw = () => {
    const q = query.toLowerCase();
    const shown = all.filter((e) => !q || text(e).includes(q));
    body.replaceChildren(shown.length ? table({
      caption: "Audit log",
      rows: shown,
      columns: [
        {label: "When", width: "170px", render: (e) => h("span", {title: e.at}, when(e.at))},
        {label: "Who", width: "140px", render: (e) => e.who},
        {label: "What", render: (e) => [h("div", {class: "primary-cell"}, e.action), e.subject ? h("div", {class: "sub", style: "overflow-wrap:anywhere"}, e.subject) : null]},
        {label: "Details", render: (e) => h("div", {class: "meta", style: "overflow-wrap:anywhere"},
          Object.entries(e.details || {}).map(([k, v], i) => [i ? " · " : "", `${k}: `,
            k === "run" ? h("a", {href: runLink(v)}, v) : Array.isArray(v) ? v.join(", ") : String(v)]))},
      ],
    }) : emptyState(all.length
      ? {ic: "search", title: "Nothing matches", text: "Try another word, such as a name, a scenario or a run."}
      : {ic: "file", title: "Nothing recorded yet", text: "Runs started, approvals, test changes, imports, schedules and settings appear here as they happen."}));
  };
  draw();
  show([{label: "Audit log"}],
    h("div", {class: "page-head"},
      h("div", {}, h("h1", {}, "Audit log"), h("p", {class: "lead"}, "Who changed what in Quartermaster, and when. Passwords, keys and test data values are never written here.")),
      h("div", {class: "row"}, button("Download CSV", {ic: "download", href: "/api/audit.csv", attrs: {download: ""}}))),
    all.length ? h("div", {class: "toolbar"}, h("div", {class: "search"}, icon("search"),
      input({type: "search", value: query, placeholder: "Search who, what or a run", "aria-label": "Search the audit log",
        oninput: (e) => { query = e.target.value; draw(); }}))) : null,
    h("div", {class: "card"}, body),
    all.length >= 1000 ? h("p", {class: "hint"}, "The newest 1,000 entries are shown. The CSV has all of them.") : null);
}
