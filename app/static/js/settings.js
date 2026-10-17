// The Settings page: general settings, game passwords, alerts, the port pool and the
// trusted certificate.
import { api, esc, toast } from "./core.js";

// ---- settings page ----
async function loadGeneral() {
  if (!document.getElementById("gen-public-host")) return;
  let cfg = {};
  try { const r = await api.get("/admin/config"); if (r && r.ok) cfg = r.data; } catch (e) { /* ignore */ }
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.value = v == null ? "" : v; };
  set("gen-public-host", cfg.public_host); set("gen-cluster", cfg.ark_cluster_id);
  set("gen-prefix", cfg.server_name_prefix);
  set("gen-secrets", cfg.secrets_conf); set("gen-sf-token", cfg.satisfactory_api_token);
  const dirs = cfg.install_dirs || {};
  set("gen-dir-ark", dirs.ark); set("gen-dir-palworld", dirs.palworld);
  set("gen-dir-valheim", dirs.valheim); set("gen-dir-satisfactory", dirs.satisfactory);
  set("gen-dir-abiotic", dirs.abiotic);
  set("bk-default-keep", cfg.default_backup_keep);
  const sched = document.getElementById("bk-sched");
  if (sched) sched.textContent = `${cfg.backup_schedule || "Daily backup"} — timer ${cfg.backup_timer_enabled ? "enabled ✓" : "disabled"}.`;
  const val = (id) => { const e = document.getElementById(id); return e ? e.value.trim() : ""; };
  const gs = document.getElementById("gen-save");
  if (gs) gs.onclick = async () => {
    const r = await api.post("/admin/config", {
      public_host: val("gen-public-host"), ark_cluster_id: val("gen-cluster"),
      server_name_prefix: val("gen-prefix"),
      secrets_conf: val("gen-secrets"), satisfactory_api_token: val("gen-sf-token"),
      install_dirs: { ark: val("gen-dir-ark"), palworld: val("gen-dir-palworld"),
        valheim: val("gen-dir-valheim"), satisfactory: val("gen-dir-satisfactory"),
        abiotic: val("gen-dir-abiotic") },
    });
    if (r) toast(r.data.ok ? "General settings saved." : (r.data.error || "Save failed."), !r.data.ok);
  };
  const bs = document.getElementById("bk-default-save");
  if (bs) bs.onclick = async () => {
    const r = await api.post("/admin/config", { default_backup_keep: Number(val("bk-default-keep")) });
    if (r) toast(r.data.ok ? "Saved." : (r.data.error || "Failed."), !r.data.ok);
  };
  const ra = document.getElementById("bk-run-all");
  if (ra) ra.onclick = async () => {
    if (!confirm("Back up ALL servers now?")) return;
    const r = await api.post("/admin/backups/run-all", {});
    if (r) toast(r.data.ok ? (r.data.message || "Started.") : (r.data.error || "Failed."), !r.data.ok);
  };
}

async function loadPasswords() {
  const status = document.getElementById("pw-status");
  if (!status) return;
  try {
    const r = await api.get("/admin/passwords");
    if (r && r.ok) {
      const d = r.data;
      status.innerHTML = `Join password: <b>${d.join_set ? "set" : "not set"}</b> · ` +
        `Admin/RCON password: <b>${d.admin_set ? "set" : "not set"}</b> · ` +
        `<span class="muted">stored in ${esc(d.secrets_path)}</span>`;
    }
  } catch (e) { /* ignore */ }
  const save = document.getElementById("pw-save");
  if (save) save.onclick = async () => {
    const join = document.getElementById("pw-join").value;
    const admin = document.getElementById("pw-admin").value;
    if (!join && !admin) { toast("Enter a new password in at least one field.", true); return; }
    const r = await api.post("/admin/passwords", { join_password: join, admin_password: admin });
    if (!r) return;
    if (r.data.ok) {
      document.getElementById("pw-join").value = "";
      document.getElementById("pw-admin").value = "";
      const who = (r.data.restart && r.data.restart.length) ? " Restart to apply: " + r.data.restart.join(", ") + "." : "";
      toast((r.data.message || "Saved.") + who);
      loadPasswords();
    } else { toast(r.data.error || "Save failed.", true); }
  };
}

export function initSettings() { loadGeneral(); loadPasswords(); loadAlerts(); loadPortPool(); initCert(); }

async function loadAlerts() {
  if (!document.getElementById("al-dests")) return;
  let services = [], dests = [];
  const box = document.getElementById("al-dests");
  const svc = (type) => services.find((s) => s.type === type);
  // read the form back into a list of destinations
  const collect = () => [...box.querySelectorAll(".al-dest")].map((card) => {
    const d = { type: card.querySelector(".al-type").value };
    card.querySelectorAll("[data-field]").forEach((i) => { d[i.dataset.field] = i.value; });
    return d;
  });
  const fieldHtml = (f, value) => {
    const tip = esc(f.help || "");
    if (f.kind.startsWith("choice:")) {
      const opts = f.kind.slice(7).split("|").map((o) =>
        `<option value="${esc(o)}"${o === value ? " selected" : ""}>${esc(o.toUpperCase())}</option>`).join("");
      return `<label title="${tip}">${esc(f.label)} <select data-field="${esc(f.name)}">${opts}</select></label>`;
    }
    const secret = f.kind === "secret";
    const saved = secret && value === "__saved__";
    return `<label title="${tip}">${esc(f.label)}
      <input type="${secret ? "password" : "text"}" data-field="${esc(f.name)}" autocomplete="off"
        value="${saved ? "__saved__" : esc(value || "")}" placeholder="${saved ? "saved" : ""}">
      <span class="muted field-help">${tip}</span></label>`;
  };
  const render = () => {
    box.innerHTML = dests.map((d, n) => {
      const s = svc(d.type) || services[0];
      const options = services.map((x) => `<option value="${esc(x.type)}"${x.type === s.type ? " selected" : ""}>${esc(x.label)}</option>`).join("");
      return `<div class="al-dest" data-n="${n}">
        <label>Send alerts to <select class="al-type">${options}</select></label>
        ${s.fields.map((f) => fieldHtml(f, d[f.name])).join("")}
        <div class="alerts-btns"><button class="ctl" data-al-test="${n}">Test</button>
          <button class="linkbtn" data-al-remove="${n}">Remove</button></div>
        <div class="al-result" id="al-result-${n}"></div></div>`;
    }).join("") || `<p class="muted hint">No alerts set up yet.</p>`;
  };
  const showResults = (results, target) => {
    const html = (results || []).map((r) => r.ok
      ? `<div class="note good">✅ ${esc(r.service)}: sent — check it arrived.</div>`
      : `<div class="note bad">❌ ${esc(r.service)}: ${esc(r.error)}</div>`).join("")
      || `<div class="note">Nothing to send to yet — add a place first.</div>`;
    document.getElementById(target).innerHTML = html;
  };
  try {
    const r = await api.get("/admin/alerts");
    if (!r || !r.ok) return;
    const a = r.data;
    services = a.services || []; dests = a.destinations || [];
    document.getElementById("al-recovery").checked = !!a.alert_on_recovery;
    document.getElementById("al-unreachable").checked = !!a.alert_on_unreachable;
    document.getElementById("al-disabled").checked = !!a.alert_on_disabled;
    render();
  } catch (e) { return; }

  const save = async (test) => {
    const body = {
      destinations: collect(), test,
      alert_on_recovery: document.getElementById("al-recovery").checked,
      alert_on_unreachable: document.getElementById("al-unreachable").checked,
      alert_on_disabled: document.getElementById("al-disabled").checked,
    };
    let r;
    try { r = await api.post("/admin/alerts", body); }
    catch (e) { toast("Couldn't reach the dashboard — nothing was saved.", true); return; }
    if (!r) return;
    const d = r.data;
    if (!d.ok) { toast(d.error || "Save failed.", true); return; }
    dests = d.destinations || []; render();
    if (test === "all") showResults(d.test_results, "al-results");
    else if (typeof test === "number") showResults(d.test_results, `al-result-${test}`);
    else toast("Alert settings saved.");
  };
  box.addEventListener("change", (e) => {
    if (!e.target.classList.contains("al-type")) return;
    const n = +e.target.closest(".al-dest").dataset.n;
    dests = collect(); dests[n] = { type: e.target.value }; render();
  });
  box.addEventListener("click", (e) => {
    const t = e.target.closest("[data-al-test]"), rm = e.target.closest("[data-al-remove]");
    if (t) { e.preventDefault(); save(+t.dataset.alTest); }
    if (rm) { e.preventDefault(); dests = collect(); dests.splice(+rm.dataset.alRemove, 1); render(); }
  });
  document.getElementById("al-add").onclick = (e) => {
    e.preventDefault(); dests = collect(); dests.push({ type: services[0].type }); render();
  };
  document.getElementById("al-save").onclick = () => save(null);
  document.getElementById("al-test").onclick = () => save("all");
}

async function loadPortPool() {
  if (!document.getElementById("pp-game-lo")) return;
  const CLASSES = ["game", "query", "rcon"];
  const setRange = (c, rng) => {
    document.getElementById(`pp-${c}-lo`).value = rng ? rng[0] : "";
    document.getElementById(`pp-${c}-hi`).value = rng ? rng[1] : "";
  };
  try {
    const r = await api.get("/admin/portpool");
    if (r && r.ok) {
      const pool = r.data.port_pool || {};
      CLASSES.forEach((c) => setRange(c, pool[c]));
    }
  } catch (e) { /* ignore */ }

  const num = (id) => { const v = document.getElementById(id).value.trim(); return v === "" ? null : Number(v); };
  const rangeOf = (c) => {
    const lo = num(`pp-${c}-lo`), hi = num(`pp-${c}-hi`);
    return (lo == null && hi == null) ? null : [lo, hi];
  };
  document.getElementById("pp-save").onclick = async () => {
    const body = {};
    CLASSES.forEach((c) => { body[c] = rangeOf(c); });
    const r = await api.post("/admin/portpool", body);
    if (!r) return;
    const d = r.data;
    toast(d.ok ? "Port pool saved." : (d.error || "Save failed."), !d.ok);
  };
}

// ---- Settings: trusted certificate (Let's Encrypt) ----
async function initCert() {
  const status = document.getElementById("cert-status");
  if (!status) return;
  const get = async () => {
    try {
      const r = await api.get("/admin/cert");
      return r && r.ok ? r.data : null;
    } catch (e) { return null; }   // expected for a moment while the dashboard restarts
  };
  const show = (d) => {
    if (!d || !d.ok) return;
    const c = d.cert;
    status.textContent = c.trusted
      ? `✅ A trusted certificate is installed${c.domain ? " for " + c.domain : ""}. It expires in ${c.days_left} days and ${c.auto_renew ? "renews itself automatically" : "is NOT set to renew automatically"}.`
      : "This dashboard is using its built-in (self-signed) certificate.";
    document.getElementById("cert-lan").textContent = d.lan_ip || "this computer";
    document.getElementById("cert-port").textContent = c.http_port;
    document.getElementById("cert-terms").href = d.terms_url;
    const dom = document.getElementById("cert-domain");
    if (!dom.value) dom.value = c.domain || (/[a-z]/i.test(d.suggest || "") ? d.suggest : "");
    const job = document.getElementById("cert-job"), j = d.job || {};
    const go = document.getElementById("cert-go");
    go.disabled = j.state === "running" || !d.available;
    if (!d.available) { job.hidden = false; job.textContent = "The certificate tool isn't installed yet — run the RealmCradle installer again to add it."; }
    else if (j.state === "running") { job.hidden = false; job.textContent = `⏳ ${j.step || "Working"}…`; }
    else if (j.state === "done" || j.state === "failed") { job.hidden = false; job.textContent = (j.state === "done" ? "✅ " : "✗ ") + (j.message || ""); }
    else job.hidden = true;
    return j.state === "running";
  };
  const watch = async () => { if (show(await get())) setTimeout(watch, 2500); };
  watch();
  document.getElementById("cert-go").onclick = async () => {
    const r = await api.post("/admin/cert", { domain: document.getElementById("cert-domain").value,
                                              email: document.getElementById("cert-email").value,
                                              agree: document.getElementById("cert-agree").checked });
    if (!r) return;
    const d = r.data;
    toast(d.ok ? d.message : (d.error || "Couldn't start the request."), !d.ok);
    if (d.ok) watch();
  };
}
