// Settings: clients and environments, sign-in, AI, evidence, storage, appearance and shortcuts.
// Passwords are never shown.
import {api, button, card, field, h, icon, input, remember, segmented, toast, when} from "./ui.js";
import {checkPod, openFolder} from "./components.js";
import {connection, envName, loadCommon, schedule, state} from "./state.js";
import {setTheme, show} from "./app.js";
import {environmentsCard} from "./page-environments.js";

export async function settingsPage() {
  await loadCommon();
  if (state.page !== "settings") return;
  const st = state.status;
  const c = connection(st);

  const row = (label, value, ok, extra) => h("div", {class: "list-item", style: "padding:12px 0"},
    h("span", {class: `icon-tile tone-${ok ? "success" : "danger"}`}, icon(ok ? "check" : "x")),
    h("div", {class: "grow"}, h("div", {class: "t"}, label), h("div", {class: "meta", style: "overflow-wrap:anywhere"}, value)), extra);

  // The environment runs use now, and how it signs in.
  const inUse = card({title: "In use now",
    sub: st.client ? `${st.client} · ${envName(st)}` : st.pod_url ? "Set in the terminal (QM_FUSION_URL)" : "Nothing set up yet",
    body: h("div", {},
      row("Pod address", st.pod_url || "No pod yet. Add a client and its environment below.", Boolean(st.pod_url)),
      row("Connection", st.pod_check ? `${c.label} · ${st.pod_check.message} · checked ${when(st.pod_check.checked_at).toLowerCase()}` : "Not checked yet",
        Boolean(st.pod_check?.ok),
        button("Check now", {size: "sm", ic: "refresh", disabled: !st.pod_url, onClick: async (e) => {
          e.currentTarget.disabled = true;
          await checkPod().catch((err) => toast(err.message));
          settingsPage();
        }})),
      st.sign_in === "sso" ? null : row("Signs in as", st.user
        ? `${st.user} · password ${st.password_set ? "saved" : "not saved yet: edit the environment below"}`
        : "No test user yet: edit the environment below.", Boolean(st.user && st.password_set)),
      byHandRow(st))});
  const environments = await environmentsCard(settingsPage);
  if (state.page !== "settings") return;

  const ai = aiCard(st.ai);

  const storage = card({title: "Storage", sub: "Where tests and evidence are kept",
    body: h("div", {class: "stack"}, h("dl", {class: "kv"},
      h("dt", {}, "Tests"), h("dd", {}, h("code", {}, st.tests_folder)),
      h("dt", {}, "Evidence"), h("dd", {}, h("code", {}, st.evidence_folder))),
    h("div", {class: "row"}, button("Open the evidence folder", {size: "sm", ic: "folder", onClick: () => openFolder(".")})))});

  // The same choices as in New run (they are shared): every run started afterwards uses them,
  // including Run on a manual scenario and the runs started from Release impact.
  const opt = {...st.default_options, ...(remember("options") || {})};
  const keep = (key, value) => {
    remember("options", {...(remember("options") || {}), screenshots: opt.screenshots, video: opt.video, headed: Boolean(opt.headed),
      highlight: opt.highlight !== false, [key]: value});
    opt[key] = value;
    toast("Saved. Runs started from now on use it.");
  };
  const headed = h("input", {type: "checkbox", checked: Boolean(opt.headed), onchange: (e) => keep("headed", e.target.checked)});
  const highlight = h("input", {type: "checkbox", checked: opt.highlight !== false, onchange: (e) => keep("highlight", e.target.checked)});
  const evidence = card({title: "Evidence", sub: "Screenshots, video and the browser, for every run you start",
    body: h("div", {class: "stack"},
      h("div", {}, h("div", {class: "label"}, "Screenshots"),
        segmented([["every-step", "Every step"], ["on-failure", "Only failures"], ["off", "None"]], opt.screenshots, (v) => keep("screenshots", v), "Screenshots"),
        h("div", {class: "hint"}, "Screenshots go into the Word evidence document of each test.")),
      h("div", {}, h("div", {class: "label"}, "Video"),
        segmented([["off", "None"], ["on-failure", "Keep on failure"], ["always", "Always"]], opt.video, (v) => keep("video", v), "Video"),
        h("div", {class: "hint"}, "Videos are kept next to the document and shown in the run's Video tab.")),
      h("label", {class: "switch"}, headed, "Show the browser while it runs"),
      h("div", {}, h("label", {class: "switch"}, highlight, "Highlight clicks"),
        h("div", {class: "hint"}, "A red box (and a red dot for a click) shows what each step clicks or fills, in the browser and the video, and a red box marks it in the screenshots. Turn off for clean pictures.")),
      h("p", {class: "hint", style: "margin:0"}, "The same choices are in New run; changing them in either place changes both. Prepare and Run by hand always show the browser."))});

  const appearance = card({title: "Appearance",
    body: segmented([["system", "Same as this computer"], ["light", "Light"], ["dark", "Dark"]],
      document.documentElement.dataset.theme || "system", setTheme, "Theme")});

  const keys = [["Ctrl K", "Search, go to or run anything"], ["/", "Search"], ["N", "New run"], ["← →", "Previous and next screenshot"],
    ["Esc", "Close a dialog or panel"]];
  const shortcuts = card({title: "Keyboard shortcuts",
    body: h("dl", {class: "kv"}, keys.flatMap(([k, d]) => [h("dt", {}, h("kbd", {}, k)), h("dd", {}, d)]))});

  show([{label: "Settings"}],
    h("div", {class: "page-head"}, h("div", {}, h("h1", {}, "Settings"), h("p", {class: "lead"}, "Environment, sign-in, AI, evidence, storage and appearance."))),
    h("div", {class: "grid g-2"}, h("div", {class: "stack"}, inUse, environments, ai), h("div", {class: "stack"}, evidence, storage, appearance, shortcuts)));
}

// The AI that prepares manual scenarios. Any provider. The key is pasted here (kept in memory only,
// until Quartermaster stops) or set on the computer; it is never stored or shown again.
function aiCard(ai) {
  const presets = Object.fromEntries(ai.presets.map((p) => [p.id, p]));
  const provider = h("select", {class: "input", "aria-label": "AI provider"},
    h("option", {value: ""}, "None (no AI)"), ai.presets.map((p) => h("option", {value: p.id, selected: p.id === ai.provider}, p.label)));
  const model = input({value: ai.provider ? ai.model : "", placeholder: "The model name, as your provider writes it", maxlength: "120"});
  const key = input({type: "password", autocomplete: "off", placeholder: ai.key_set ? "Saved (hidden). Paste a new key to change it" : "Paste your API key", "aria-label": "API key"});
  const baseUrl = input({value: ai.provider ? ai.base_url : "", placeholder: "https://…", maxlength: "300"});
  const keyEnv = input({value: ai.provider ? ai.key_env : "", placeholder: "e.g. OPENAI_API_KEY", maxlength: "80"});
  const workspace = input({value: ai.workspace || "", placeholder: "e.g. wrkspc_01…", maxlength: "100"});
  const workspaceRow = h("div", {}, field("Workspace ID (Anthropic only)", workspace,
    "Only needed if Anthropic says the key is not scoped to a workspace. Find it in the Anthropic Console, under Workspaces.", "ai-workspace"));
  const drawWorkspace = () => { workspaceRow.style.display = presets[provider.value]?.format === "anthropic" ? "" : "none"; };
  let previous = presets[ai.provider];
  const keyRow = h("div", {});
  const drawKeyRow = () => {
    const p = presets[provider.value];
    const needsKey = provider.value && (keyEnv.value || (p && p.key_env));
    keyRow.style.display = needsKey ? "" : "none";
  };
  provider.onchange = () => {
    const p = presets[provider.value];
    // Fill in what the provider uses, unless the reader typed something of their own.
    for (const [el, k] of [[baseUrl, "base_url"], [keyEnv, "key_env"], [model, "model"]]) {
      if (!el.value || (previous && el.value === previous[k])) el.value = p ? p[k] : "";
    }
    previous = p;
    drawKeyRow();
    drawWorkspace();
  };
  const keyNote = ai.key_source === "entered" ? "A key is saved. It is kept in memory only: paste it again after you restart Quartermaster."
    : ai.key_source === "computer" ? `A key is set on this computer (${ai.key_env}).` : "Kept in memory only, until Quartermaster stops. Never written to a file or shown again.";
  keyRow.append(field("API key", key, keyNote, "ai-key-value"));
  drawKeyRow();
  drawWorkspace();
  const result = h("div", {class: "meta", role: "status", "aria-live": "polite"});
  const save = button("Save", {kind: "primary", onClick: async (e) => {
    e.currentTarget.disabled = true;
    try {
      await api("/api/settings", {ai_provider: provider.value, ai_model: model.value.trim(), ai_base_url: baseUrl.value.trim(), ai_key_env: keyEnv.value.trim(), ai_workspace: workspace.value.trim()});
      if (key.value.trim()) await api("/api/ai/key", {key: key.value.trim()});
      key.value = "";
      toast("Saved.");
      settingsPage();
    } catch (err) { toast(err.message); e.currentTarget.disabled = false; }
  }});
  const test = button("Test the AI", {ic: "refresh", disabled: !ai.provider || Boolean(ai.problem), title: ai.problem || "Ask the saved AI a one-word question", onClick: async (e) => {
    e.currentTarget.disabled = true;
    result.textContent = "Asking…";
    result.style.color = "";
    try { const r = await api("/api/ai/check", {}); result.textContent = r.message; result.style.color = r.ok ? "var(--success)" : "var(--danger)"; }
    catch (err) { result.textContent = err.message; }
    e.currentTarget.disabled = false;
  }});
  const forget = ai.key_source === "entered" ? button("Forget the key", {kind: "ghost", onClick: async () => {
    try { await api("/api/ai/key", {key: ""}); toast("The key is forgotten."); settingsPage(); } catch (err) { toast(err.message); }
  }}) : null;
  return card({title: "AI assistant", sub: "Prepares manual scenarios automatically. Choose any provider.",
    body: h("div", {class: "stack"},
      h("div", {class: "fields"},
        field("Provider", provider, "Any OpenAI-compatible service works with Other.", "ai-provider"),
        field("Model", model, "The model name shown in your provider's account.", "ai-model"),
        h("div", {class: "wide"}, keyRow)),
      ai.provider ? h("div", {class: "row", style: "gap:8px;flex-wrap:nowrap"},
        h("span", {class: `icon-tile tone-${ai.problem ? "danger" : "success"}`}, icon(ai.problem ? "x" : "check")),
        h("span", {class: "meta"}, ai.problem || `Ready: ${ai.label}.${ai.key_env ? " Key saved (hidden)." : ""}`)) : null,
      h("div", {class: "row"}, save, test, forget), result,
      h("details", {class: "disclose"}, h("summary", {}, icon("right"), "Advanced: web address, key variable, workspace"),
        h("div", {class: "fields", style: "margin-top:12px"},
          h("div", {class: "wide"}, field("Web address", baseUrl, "Filled in for the providers in the list. For Other, use the provider's OpenAI-compatible address.", "ai-url")),
          field("Key variable", keyEnv, "Instead of pasting the key, you can set this variable on the computer before starting qm serve; then it is remembered after a restart.", "ai-key"),
          h("div", {class: "wide"}, workspaceRow))),
      h("p", {class: "hint"}, "What is sent to the AI: the scenario's written steps and the names of the buttons, links and headings on the pod screen. E-mail addresses and long numbers are hidden first. Never typed values, never the pod password. Use a test pod."))});
}

// Single sign-on or MFA: the pod will not take a user name and password from a test, so a person
// signs in once in a browser Quartermaster opens. The session stays in memory, never in a file.
function byHandRow(st) {
  const sh = st.signed_in_by_hand || {status: "none"};
  const start = async (e) => {
    e.currentTarget.disabled = true;
    try { await api("/api/signin", {}); toast("A browser opened on the pod. Sign in there; it closes by itself."); settingsPage(); }
    catch (err) { toast(err.message); e.currentTarget.disabled = false; }
  };
  const text = {
    none: "Not used. For a pod behind single sign-on or MFA, sign in by hand once; runs then use that sign-in.",
    waiting: "Waiting for you to sign in, in the browser that opened…",
    done: `Signed in by hand${sh.at ? ` ${when(sh.at).toLowerCase()}` : ""}. Runs use it until the pod ends the session or Quartermaster stops. It is kept in memory only.`,
    failed: `Did not work: ${sh.error || "the browser closed"}.`,
  }[sh.status] || "";
  const actions = sh.status === "waiting" ? null : [
    button(sh.status === "done" ? "Sign in again" : "Sign in by hand", {size: "sm", ic: "lock", disabled: !st.pod_url, onClick: start}),
    sh.status === "done" ? button("Forget", {size: "sm", kind: "ghost", onClick: async () => {
      try { await api("/api/signin/forget", {}); toast("Forgotten."); settingsPage(); } catch (err) { toast(err.message); }
    }}) : null,
  ];
  if (sh.status === "waiting") schedule(settingsPage, 2000);
  const tone = {done: ["success", "check"], failed: ["danger", "x"], waiting: ["info", "loader"]}[sh.status] || ["neutral", "lock"];
  return h("div", {class: "list-item", style: "padding:12px 0"},
    h("span", {class: `icon-tile tone-${tone[0]}`}, icon(tone[1])),
    h("div", {class: "grow"}, h("div", {class: "t"}, "Single sign-on or MFA"), h("div", {class: "meta", style: "overflow-wrap:anywhere"}, text)),
    actions ? h("div", {class: "row", style: "gap:6px"}, actions) : null);
}
