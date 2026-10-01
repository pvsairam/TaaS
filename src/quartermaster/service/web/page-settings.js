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

  const ai = aiCard(st.ai);

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
    h("div", {class: "grid g-2"}, h("div", {class: "stack"}, environment, signin, ai), h("div", {class: "stack"}, storage, appearance, shortcuts)));
}

// The AI that prepares manual scenarios. Any provider: the key stays in an environment variable.
function aiCard(ai) {
  const presets = Object.fromEntries(ai.presets.map((p) => [p.id, p]));
  const provider = h("select", {class: "input", "aria-label": "AI provider"},
    h("option", {value: ""}, "None (no AI)"), ai.presets.map((p) => h("option", {value: p.id, selected: p.id === ai.provider}, p.label)));
  const model = input({value: ai.provider ? ai.model : "", placeholder: "The model name, as your provider writes it", maxlength: "120"});
  const baseUrl = input({value: ai.provider ? ai.base_url : "", placeholder: "https://…", maxlength: "300"});
  const keyEnv = input({value: ai.provider ? ai.key_env : "", placeholder: "e.g. OPENAI_API_KEY", maxlength: "80"});
  let previous = presets[ai.provider];
  provider.onchange = () => {
    const p = presets[provider.value];
    // Fill in what the provider uses, unless the reader typed something of their own.
    for (const [el, key] of [[baseUrl, "base_url"], [keyEnv, "key_env"], [model, "model"]]) {
      if (!el.value || (previous && el.value === previous[key])) el.value = p ? p[key] : "";
    }
    previous = p;
    hint.textContent = keyHint();
  };
  const keyHint = () => keyEnv.value ? `Set it like the pod password: $env:${keyEnv.value}="your key", then restart qm serve.` : "This provider needs no key.";
  const hint = h("span", {}, keyHint());
  keyEnv.oninput = () => { hint.textContent = keyHint(); };
  const result = h("div", {class: "meta", role: "status", "aria-live": "polite"});
  const save = button("Save", {kind: "primary", onClick: async (e) => {
    e.currentTarget.disabled = true;
    try {
      await api("/api/settings", {ai_provider: provider.value, ai_model: model.value.trim(), ai_base_url: baseUrl.value.trim(), ai_key_env: keyEnv.value.trim()});
      toast("Saved.");
      settingsPage();
    } catch (err) { toast(err.message); e.currentTarget.disabled = false; }
  }});
  const test = button("Test the AI", {ic: "refresh", disabled: !ai.provider, title: "Ask the saved AI a one-word question", onClick: async (e) => {
    e.currentTarget.disabled = true;
    result.textContent = "Asking…";
    try { const r = await api("/api/ai/check", {}); result.textContent = r.message; result.style.color = r.ok ? "var(--success)" : "var(--danger)"; }
    catch (err) { result.textContent = err.message; }
    e.currentTarget.disabled = false;
  }});
  return card({title: "AI assistant", sub: "Prepares manual scenarios automatically. Choose any provider.",
    body: h("div", {class: "stack"},
      h("div", {class: "fields"},
        h("div", {class: "wide"}, field("Provider", provider, "OpenAI-compatible services (most of them) work with Other.", "ai-provider")),
        field("Model", model, "For example the model id shown in your provider's account.", "ai-model"),
        field("Key variable", keyEnv, hint, "ai-key"),
        h("div", {class: "wide"}, field("Web address", baseUrl, "Filled in for the providers above. For Other, use the provider's OpenAI-compatible address.", "ai-url"))),
      ai.provider ? h("div", {class: "row", style: "gap:8px"},
        h("span", {class: `icon-tile tone-${ai.problem ? "danger" : "success"}`}, icon(ai.problem ? "x" : "check")),
        h("span", {class: "meta"}, ai.problem || `Ready: ${ai.label}. Key ${ai.key_env ? "set (hidden)" : "not needed"}.`)) : null,
      h("div", {class: "row"}, save, test), result,
      h("p", {class: "hint"}, "What is sent to the AI: the scenario's written steps and the names of the buttons, links and headings on the pod screen. E-mail addresses and long numbers are hidden first. Use a test pod. The key is never stored by Quartermaster."))});
}
