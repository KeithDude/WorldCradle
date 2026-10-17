// The Games panel (install and uninstall game servers) and the Add-a-server form.
import { loadChecklist, refreshAdminNow } from "./admin.js";
import { api, esc, pill, poll, safeUrl, toast } from "./core.js";

// ---- Games panel: what's installed, and install the rest ----
const gamesState = { lastJob: "", wired: false };

export async function loadGames() {
  const list = document.getElementById("games-list");
  if (!list) return;
  let d = null;
  try {
    const r = await api.get("/admin/games");
    if (!r) return;
    d = r.data;
  } catch (e) { /* ignore */ }
  if (!d || !d.ok) { list.textContent = "Couldn't load the games list."; return; }
  const busy = d.job && d.job.state === "running";
  const n = d.games.filter((g) => g.installed).length;
  document.getElementById("games-sum").textContent = `— ${n} of ${d.games.length} installed`;
  const tn = document.getElementById("games-terms");
  if (tn && safeUrl(d.steam_terms)) {
    tn.innerHTML = `Most servers here are downloaded from Steam. Installing one means you accept the <a href="${esc(d.steam_terms)}" target="_blank" rel="noopener noreferrer">Steam Subscriber Agreement</a> and the game publisher's own terms, linked under each game where the publisher provides them.`;
  }
  list.innerHTML = d.games.map((g) => {
    const need = g.missing.length
      ? `<div class="g-need bad">Needs ${esc(g.missing.join(", "))} on this computer first — run the GameDash installer again to add it.</div>`
      : `<div class="g-need">About ${esc(g.size_gb)} GB of disk${g.ram_note ? " · " + esc(g.ram_note) : ""}</div>`;
    const side = g.installed
      ? pill("on", "installed") + `<button class="linkbtn hint-sm" data-uninstall="${esc(g.kind)}" data-label="${esc(g.label)}">Uninstall</button>`
      : `<button class="ctl go" data-install="${esc(g.kind)}" data-label="${esc(g.label)}" data-size="${esc(g.size_gb)}" data-free="${esc(g.free_gb)}"${(busy || g.missing.length) ? " disabled" : ""}>Install</button>`;
    const terms = (g.eula && safeUrl(g.eula.url))
      ? `<div class="g-need">Terms: <a href="${esc(g.eula.url)}" target="_blank" rel="noopener noreferrer">${esc(g.eula.name)}</a>${g.eula.required ? " — you'll be asked to agree when you add a server" : ""}</div>`
      : "";
    return `<div class="game-row">
      <div class="g-main"><div class="g-title">${esc(g.title)}</div>
        <div class="g-about">${esc(g.about)}</div>${need}${terms}</div>
      <div class="g-side">${side}</div></div>`;
  }).join("");
  if (!gamesState.wired) {
    gamesState.wired = true;
    list.addEventListener("click", async (e) => {
      const u = e.target.closest("button[data-uninstall]");
      if (u) {
        if (!confirm(`Uninstall ${u.dataset.label}?\n\nThis deletes the game's server files from this computer. ` +
                     `You can install it again later. Servers you created for it must be removed first.`)) return;
        const r = await api.post("/admin/games/uninstall", { kind: u.dataset.uninstall });
        if (!r) return;
        const res = r.data;
        toast(res.ok ? res.message : (res.error || "Couldn't uninstall."), !res.ok);
        loadGames(); loadChecklist();
        const add = document.getElementById("as-submit");
        if (add) { add._wired = false; wireAddServer(); }
        return;
      }
      const b = e.target.closest("button[data-install]");
      if (!b) return;
      const free = b.dataset.free ? ` (this computer has ${b.dataset.free} GB free)` : "";
      if (!confirm(`Install ${b.dataset.label}?\n\nThis downloads about ${b.dataset.size} GB${free}. ` +
                   `It can take a while on a slow connection — you can keep using the dashboard meanwhile.`)) return;
      b.disabled = true;
      try {
        const r = await api.post("/admin/games/install", { kind: b.dataset.install });
        if (!r) return;
        const res = r.data;
        toast(res.ok ? res.message : (res.error || "Couldn't start the install."), !res.ok);
        if (res.ok) { refreshAdminNow(); loadGames(); } else { b.disabled = false; }
      } catch (err) { toast("Couldn't start the install.", true); b.disabled = false; }
    });
  }
}

// called on every admin poll with the install job's state
export function renderInstallJob(job) {
  const box = document.getElementById("games-job");
  if (!box) return;
  const sig = job ? `${job.state}:${job.kind || ""}` : "";
  if (job && job.state === "running") {
    box.hidden = false;
    document.getElementById("games-panel").open = true;
    document.getElementById("games-job-text").textContent =
      `Installing ${job.label}: ${job.step || "working"}${job.percent ? ` — ${job.percent}%` : ""}`;
    document.getElementById("games-job-bar").style.width = `${Math.min(100, job.percent || 0)}%`;
  } else if (job && (job.state === "done" || job.state === "failed")) {
    box.hidden = false;
    document.getElementById("games-job-text").textContent = (job.state === "done" ? "✓ " : "✗ ") + (job.message || "");
    document.getElementById("games-job-bar").style.width = job.state === "done" ? "100%" : "0";
  } else { box.hidden = true; }
  if (sig !== gamesState.lastJob) {        // started or finished → refresh the lists that depend on it
    const first = gamesState.lastJob === "";
    gamesState.lastJob = sig;
    if (!first) {
      loadGames(); loadChecklist();
      const add = document.getElementById("as-submit");   // rebuild the Add form's game list
      if (add) { add._wired = false; wireAddServer(); }
    }
  }
}

export async function wireAddServer() {
  const b = document.getElementById("as-submit");
  if (!b || b._wired) return;
  b._wired = true;
  const kindSel = document.getElementById("as-kind");
  let types = [];
  try {
    const r = await api.get("/admin/servers/types");
    if (r && r.ok) types = r.data.types || [];
  } catch (e) { /* ignore */ }
  const keep = kindSel.value;   // re-wired after an install finishes: keep the selection
  kindSel.innerHTML = types.map((t) => `<option value="${esc(t.kind)}">${esc(t.label)}${t.installed === false ? " — not installed yet" : ""}</option>`).join("");
  if (keep && types.some((t) => t.kind === keep)) kindSel.value = keep;

  // Is a port pool configured? Gate the "use port pool" checkbox on it.
  let poolReady = false;
  try {
    const pr = await api.get("/admin/portpool");
    if (pr && pr.ok) poolReady = Object.keys(pr.data.port_pool || {}).length > 0;
  } catch (e) { /* ignore */ }
  const poolCk = document.getElementById("as-pool");
  const poolNote = document.getElementById("as-pool-note");
  poolCk.disabled = !poolReady;
  if (!poolReady) poolCk.checked = false;
  poolNote.textContent = poolReady ? "(allocate ports from the pool)" : "(no pool configured)";
  document.getElementById("as-pool-wrap").hidden = !poolReady;   // nothing to offer without a pool

  // per-game descriptions come from the server (each game type's provision_hint)
  const CUSTOM_HINT = "Custom service — run any game/server we don't natively support. Give the exact launch command (executable + arguments), its working directory, and the port players connect to. An optional query port enables Steam A2S player counts. It runs as a managed service you can start/stop/log/remove from here.";
  // One Add-form option, rendered by its declared type (text is the default).
  // Every option carries data-extra=<name>; the submit handler reads them back.
  const extraField = (f) => {
    const tip = f.help ? ` title="${esc(f.help)}"` : "";
    const name = esc(f.name);
    const def = f.default == null ? "" : f.default;
    if (f.type === "checkbox") {
      return `<label class="ck"${tip}><input type="checkbox" data-extra="${name}"${def ? " checked" : ""}> ${esc(f.label)}</label>`;
    }
    if (f.type === "select") {
      const opts = (f.options || []).map((o) => {
        const [v, l] = Array.isArray(o) ? o : [o, o];
        return `<option value="${esc(v)}"${String(v) === String(def) ? " selected" : ""}>${esc(l)}</option>`;
      }).join("");
      return `<label${tip}>${esc(f.label)} <select data-extra="${name}">${opts}</select></label>`;
    }
    if (f.type === "number") {
      const lim = (k) => (f[k] == null ? "" : ` ${k}="${esc(f[k])}"`);
      return `<label${tip}>${esc(f.label)} <input type="number" data-extra="${name}" value="${esc(def)}" placeholder="${esc(f.placeholder || "")}"${lim("min")}${lim("max")} step="${esc(f.step == null ? 1 : f.step)}"></label>`;
    }
    return `<label${tip}>${esc(f.label)} <input type="text" data-extra="${name}" value="${esc(def)}" placeholder="${esc(f.placeholder || "")}" autocomplete="off"></label>`;
  };
  // The publisher's licence terms. Required ones get a tick box (the server
  // refuses to create anything without it); the rest are a link for information.
  const eulaField = (t) => {
    const e = t.eula;
    if (!e || !safeUrl(e.url)) return "";
    const link = `<a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.name)}</a>`;
    return e.required
      ? `<label class="ck eula"><input type="checkbox" data-extra="eula"> <span>I have read and agree to the ${link} (opens in a new tab). The game's publisher requires this of whoever runs a server.</span></label>`
      : `<div class="eula-note">Running this server is covered by the publisher's terms: ${link}.</div>`;
  };
  // when "use port pool" is on, the custom port textboxes are filled by the
  // pool — gray them out.
  const syncPortBoxes = () => {
    const on = poolCk.checked && !poolCk.disabled;
    ["as-port", "as-qport"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) { el.disabled = on; el.classList.toggle("dim", on); }
    });
  };
  poolCk.onchange = syncPortBoxes;
  const render = () => {
    const t = types.find((x) => x.kind === kindSel.value) || { custom: true, extra_fields: [] };
    document.getElementById("as-custom").hidden = !t.custom;
    document.getElementById("as-extra").innerHTML = eulaField(t) + (t.extra_fields || []).map(extraField).join("");
    const profiles = t.mod_profiles || [];
    const pw = document.getElementById("as-profile-wrap");
    const psel = document.getElementById("as-profile");
    if (profiles.length > 1) {
      psel.innerHTML = profiles.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join("");
      pw.hidden = false;
    } else { pw.hidden = true; psel.innerHTML = ""; }
    const note = t.note ? `\n\n⚠ ${t.note}` : "";
    const missing = t.installed === false;
    document.getElementById("as-hint").textContent = missing
      ? `${t.label} isn't installed on this computer yet. Open “Games” above and press Install, then come back here.`
      : (t.custom ? CUSTOM_HINT : (t.hint || "")) + note;
    b.disabled = missing;
    syncPortBoxes();
  };
  kindSel.onchange = render;
  render();
  const nameBox = document.getElementById("as-name"), keyBox = document.getElementById("as-key");
  if (nameBox && keyBox && !nameBox._slugWired) {
    nameBox._slugWired = true;
    keyBox.addEventListener("input", () => { keyBox._touched = keyBox.value !== ""; });
    nameBox.addEventListener("input", () => {
      if (keyBox._touched) return;
      keyBox.value = nameBox.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 30);
    });
  }

  const val = (id) => { const e = document.getElementById(id); return e ? e.value.trim() : ""; };
  // Shared-ports confirmation. Resolves true ("continue") or false ("go back").
  // `conflicts` = [{port, label, servers:[names]}] from the server.
  const postAdd = (spec) => api.post("/admin/servers/add", spec);
  b.onclick = async () => {
    const t = types.find((x) => x.kind === kindSel.value) || { custom: true };
    const usePool = poolCk.checked && !poolCk.disabled;
    const spec = { kind: kindSel.value, name: val("as-name"), key: val("as-key"),
                   use_pool: usePool,
                   start: document.getElementById("as-start").checked };
    if (t.custom) {
      spec.exec_start = val("as-exec"); spec.working_dir = val("as-dir");
      spec.save_root = val("as-save");
      if (!usePool) { spec.game_port = val("as-port"); spec.query_port = val("as-qport") || null; }
    } else {
      document.querySelectorAll("#as-extra [data-extra]").forEach((i) => {
        spec[i.dataset.extra] = i.type === "checkbox" ? i.checked : i.value.trim();
      });
      const pw = document.getElementById("as-profile-wrap");
      if (pw && !pw.hidden) spec.profile = document.getElementById("as-profile").value;
    }
    b.disabled = true;
    try {
      let res = await postAdd(spec);
      if (!res) return;
      // clone-install games (Palworld) ask to confirm the disk cost first
      if (res.status === 409 && res.data.confirm_required && res.data.provision) {
        const p = res.data.provision;
        const ok = confirm(
          `${t.label} can't share an install, so a separate copy will be created:\n\n` +
          `• Disk needed: ~${p.needed_gb} GB   (free: ${p.free_gb} GB)\n` +
          `• New install: ${p.dst}\n` +
          `• A running instance also uses RAM (free now: ${p.ram_avail_gb} GB)\n\n` +
          `Create it? The copy runs in the background and the card appears when ready.`);
        if (!ok) { toast("Cancelled.", true); return; }
        res = await postAdd({ ...spec, confirm: true });
        if (!res) return;
      }
      const d = res.data;
      toast(d.ok ? (d.message || "Added.") : (d.error || "Add failed."), !d.ok);
      if (d.ok) setTimeout(refreshAdminNow, 1200);
    } catch (e) { toast("Add failed.", true); }
    finally { b.disabled = false; }
  };
}
