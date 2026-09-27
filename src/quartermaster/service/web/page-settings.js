// Settings: environment, sign-in, storage, appearance and shortcuts. Passwords are never shown.
import {api, button, card, field, h, icon, input, segmented, toast, when} from "./ui.js";
import {checkPod, openFolder} from "./components.js";
import {connection, envName, loadCommon, state} from "./state.js";
import {setTheme, show} from "./app.js";

export async function settingsPage() {
  await loadCommon();
  if (state.page !== "settings") return;
  const st = state.status;
  const c = connection(st);

  const name = input({value: st.environment_name, placeholder: envName({pod_host: st.pod_host}) || "e.g. EIIV DEV2", maxlength: "40"});
  const release = input({value: st.release, placeholder: "e.g. 26C", maxlength: "20"});
  const save = button("Save", {kind: "primary", onClick: async (e) => {
    e.currentTarget.disabled = true;
    try {
      await api("/api/settings", {environment_name: name.value.trim(), release: release.value.trim()});
      toast("Saved.");
      settingsPage();
    } catch (err) { toast(err.message); e.currentTarget.disabled = false; }
  }});

  const row = (label, value, ok, extra) => h("div", {class: "list-item", style: "padding:12px 0"},
    h("span", {class: `icon-tile tone-${ok ? "success" : "danger"}`}, icon(ok ? "check" : "x")),
    h("div", {class: "grow"}, h("div", {class: "t"}, label), h("div", {class: "meta", style: "overflow-wrap:anywhere"}, value)), extra);

  const environment = card({title: "Environment", sub: "The Oracle Fusion pod tests run on",
    body: h("div", {class: "stack"},
      h("div", {class: "fields"},
        field("Name", name, "How this environment is shown, e.g. EIIV DEV2.", "set-name"),
        field("Oracle release", release, "The release this pod is on. New runs are labelled with it.", "set-release")),
      h("div", {class: "row"}, save),
      h("div", {style: "border-top:1px solid var(--border);margin-top:4px"},
        row("Pod address", st.pod_url || "Not set. Set QM_FUSION_URL on this computer.", Boolean(st.pod_url)),
        row("Connection", st.pod_check ? `${c.label} · ${st.pod_check.message} · checked ${when(st.pod_check.checked_at).toLowerCase()}` : "Not checked yet",
          Boolean(st.pod_check?.ok),
          button("Check now", {size: "sm", ic: "refresh", disabled: !st.pod_url, onClick: async (e) => {
            e.currentTarget.disabled = true;
            await checkPod().catch((err) => toast(err.message));
            settingsPage();
          }}))))});

  const signin = card({title: "Sign-in", sub: "Used to sign in to the pod; never shown or stored by Quartermaster",
    body: h("div", {},
      row("User name", st.user || "Not set. Set QM_FUSION_USER on this computer.", Boolean(st.user)),
      row("Password", st.password_set ? "Set (hidden)" : "Not set. Set QM_FUSION_PASSWORD on this computer.", st.password_set),
      h("p", {class: "hint", style: "margin-top:12px"}, "The pod address, user and password come from environment variables on this computer. To change them, set the variables, stop Quartermaster with Ctrl+C and run ",
        h("code", {}, "qm serve"), " again. Use a test or development pod only, never production."))});

  const storage = card({title: "Storage", sub: "Where tests and evidence are kept",
    body: h("div", {class: "stack"}, h("dl", {class: "kv"},
      h("dt", {}, "Tests"), h("dd", {}, h("code", {}, st.tests_folder)),
      h("dt", {}, "Evidence"), h("dd", {}, h("code", {}, st.evidence_folder))),
    h("div", {class: "row"}, button("Open the evidence folder", {size: "sm", ic: "folder", onClick: () => openFolder(".")})))});

  const appearance = card({title: "Appearance",
    body: segmented([["system", "Same as this computer"], ["light", "Light"], ["dark", "Dark"]],
      document.documentElement.dataset.theme || "system", setTheme, "Theme")});

  const keys = [["Ctrl K", "Search, go to or run anything"], ["/", "Search"], ["N", "New run"], ["← →", "Previous and next screenshot"],
    ["Esc", "Close a dialog or panel"]];
  const shortcuts = card({title: "Keyboard shortcuts",
    body: h("dl", {class: "kv"}, keys.flatMap(([k, d]) => [h("dt", {}, h("kbd", {}, k)), h("dd", {}, d)]))});

  show([{label: "Settings"}],
    h("div", {class: "page-head"}, h("div", {}, h("h1", {}, "Settings"), h("p", {class: "lead"}, "Environment, sign-in, storage and appearance."))),
    h("div", {class: "grid g-2"}, h("div", {class: "stack"}, environment, signin), h("div", {class: "stack"}, storage, appearance, shortcuts)));
}
