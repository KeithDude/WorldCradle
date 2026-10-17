// The signed-in dashboard: the server cards and their buttons, the computer's resource use,
// operating-system updates and the Getting started checklist.
import { api, esc, fmtDur, pill, poll, reachPill, stamp, toast } from "./core.js";
import { loadGames, renderInstallJob, wireAddServer } from "./games-panel.js";
import { doAction } from "./server-actions.js";
import { DASH, applyFeed, cardHead, gameTitle, joinButton, playersBlock, rows, wireJoin } from "./servers.js";

const ACTION_TITLES = {
  reach: "Which ports to open on your router for this server, and a check of whether people outside your home can reach it",
  start: "Start this server",
  restart: "Turn the server off and on again. If anyone is playing you'll be warned first",
  stop: "Turn the server off. If anyone is playing you'll be warned first",
  kill: "Emergency only: stops the server instantly WITHOUT saving. Anything since the game's last autosave is lost. Use Stop unless the server is frozen",
  save: "Save the game world right now",
  broadcast: "Send a message to everyone playing on this server",
  chat: "Open a live in-game chat feed (ARK) — read recent chat and send messages",
  logs: "See what the server has been printing — useful when something isn't working",
  update: "Download the newest version of the game. The server is turned off for a few minutes while it updates, then started again",
  removesrv: "Remove this server from the dashboard. Its saved world stays on the disk",
  editscript: "Advanced: edit the commands that start this server (for mods or special options). Applies the next time it starts",
  backups: "Make a copy of this server's saved world, or bring an earlier copy back",
};

function controlsRow(v) {
  const can = (action) => (v.actions || []).includes(action);   // what this game supports
  const btn = (action, label, cls) =>
    `<button class="ctl ${cls || ""}" data-action="${action}" title="${esc(ACTION_TITLES[action] || "")}">${label}</button>`;
  // Start, or Restart / Stop / Force stop; then Remove and Save
  const life = v.online ? [btn("restart", "Restart", "warn"), btn("stop", "Stop", "danger"),
                           btn("kill", "Force stop", "danger")]
                        : [btn("start", "Start", "go")];
  if (v.managed === "gamedash") life.push(btn("removesrv", "Remove", "danger"));
  if (v.online && can("save")) life.push(btn("save", "Save"));
  // the other buttons, after a thin divider
  const editBtn = v.managed === "gamedash" ? btn("editscript", "Launch script") : "";
  const bkBtn = `<a class="ctl" href="/admin/backups#bk-${esc(v.key)}" title="${esc(ACTION_TITLES.backups)}">Backups</a>`;
  const acts = (v.online
    ? [can("broadcast") ? btn("broadcast", "Message") : "",
       can("chat") ? btn("chat", "Chat") : "",
       btn("logs", "Logs"), bkBtn, editBtn, btn("reach", "Can friends connect?")]
    : [btn("logs", "Logs"), bkBtn, editBtn, btn("reach", "Can friends connect?")]).filter(Boolean);
  const divider = acts.length ? '<span class="ctl-divider"></span>' : "";
  return `<div class="controls">${life.join("")}${divider}${acts.join("")}</div>`;
}

const ADMIN_FEED = "/api/admin.json";
export async function refreshAdminNow() {
  try {
    const r = await api.get(ADMIN_FEED);
    if (r && r.ok) renderAdmin(r.data);
  } catch (e) { /* the next poll will catch up */ }
}

function renderAdmin(snap) {
  const grid = document.getElementById("grid");
  if (!grid) return;
  applyFeed(snap);
  let lastGame = null;
  grid.innerHTML = Object.values(snap.servers).map((v) => {
    const game = v.name.split(" · ")[0];
    const head = game !== lastGame ? `<h3 class="group-head">${esc(gameTitle(game))}</h3>` : "";
    lastGame = game;
    const detail = v.player_detail || [];
    const names = detail.length ? `<div class="names">${detail.map((p) => `
      <div class="prow"><span class="who">👤 ${esc(p.name)}</span>${p.id ? `
        <span class="prow-btns">
          <button class="ctl warn" data-action="kick" data-target="${esc(p.id)}" data-name="${esc(p.name)}" title="Disconnect ${esc(p.name)} from the server">Kick</button>
          <button class="ctl danger" data-action="ban" data-target="${esc(p.id)}" data-name="${esc(p.name)}" title="Ban ${esc(p.name)} from the server">Ban</button>
        </span>` : ""}</div>`).join("")}</div>` : "";
    const note = (v.note ? `<div class="note">⚠ ${esc(v.note)}</div>` : "")
      + (v.backup_warn ? `<div class="note">⚠ ${esc(v.backup_warn)}</div>` : "")
      + (v.crash_warn ? `<div class="note bad">🔥 ${esc(v.crash_warn)}</div>` : "");
    const ports = esc(`game ${v.game_port}${v.query_port ? " · query " + v.query_port : ""}${v.rcon_port ? " · admin console " + v.rcon_port : ""}`);
    const answering = rows(v).answering ? `
      <dt title="Is the server answering on its port?">answering</dt><dd>${v.online && v.reachable != null ? reachPill(v) : DASH}</dd>` : "";
    const usage = !v.online ? DASH
      : `${v.cpu_percent == null ? "…" : esc(v.cpu_percent) + "%"} · ${v.mem_mb == null ? "…" : esc(v.mem_mb >= 1024 ? (v.mem_mb / 1024).toFixed(1) + " GB" : v.mem_mb + " MB")}`;
    const live = answering + `
      <dt title="This server's share of the whole computer's processor (the same scale as Total CPU usage at the top), and the memory (RAM) used by all of its processes">CPU / RAM</dt><dd>${usage}</dd>`;
    const s = v.sf || {};
    const sf = rows(v).server_stats ? `
      <dt title="Server simulation rate — 30 is healthy; consistently lower means it's struggling">tick rate</dt><dd>${v.sf ? `${esc(s.tick)}/30 ${s.paused ? pill("warn", "paused") : ""}` : DASH}</dd>
      <dt title="Game progression (tech tier / project assembly phase)">progress</dt><dd>${v.sf ? `${s.tier != null ? "Tier " + esc(s.tier) : ""}${s.phase != null ? " · Phase " + esc(s.phase) : ""}` : DASH}</dd>
      <dt title="Total in-game time elapsed in this save">game time</dt><dd>${v.sf ? fmtDur(s.uptime_s) : DASH}</dd>` : "";
    const u = (v.steam_app != null && snap.updates) ? snap.updates[String(v.steam_app)] : null;
    const job = snap.update_job;
    const updatingThis = job && job.state === "running" && job.app === v.steam_app;
    const anyUpdating = job && job.state === "running";
    let updRow = "";
    if (v.steam_app != null) {
      let cell;
      if (updatingThis) cell = pill("warn", "updating…") + ` <span class="muted">${esc(job.step || "")}</span>`;
      else if (!u) cell = pill("warn", "checking…");
      else if (!u.ok) cell = pill("warn", "check failed");
      else if (u.up_to_date) cell = pill("on", "up to date");
      else cell = pill("bad", "update available") + ` <span class="muted">${esc(u.installed)} → ${esc(u.latest)}</span>`;
      const gname = v.name.split(" · ")[0];
      const btnUpd = (!anyUpdating)
        ? ` <button class="ctl warn" data-action="update" data-app="${esc(v.steam_app)}" data-gname="${esc(gname)}">Update now</button>` : "";
      updRow = `<dt title="Whether this game has a newer version available (checked every 6 hours)">version</dt><dd>${cell}${btnUpd}</dd>`;
    }
    return head + `
    <div class="card ${v.online ? "" : "off"}" data-key="${esc(v.key)}" data-name="${esc(v.name)}">
      ${joinButton(v)}
      ${cardHead(v)}
      ${playersBlock(v)}
      ${names}
      ${note}
      <dl class="meta">
        ${live}
        ${sf}
        <dt title="The network ports this server uses. Press “Can friends connect?” to see which ones your router needs to pass through">ports</dt><dd>${ports}</dd>
        ${updRow}
      </dl>
      ${controlsRow(v)}
    </div>`;
  }).join("");

  const b = snap.box || {};
  const set = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
  set("b-cpu", (b.cpu_percent ?? 0) + "%");
  set("b-load", (b.load ? b.load[0] : 0));
  set("b-mem", `${b.mem_used_gb} / ${b.mem_total_gb} GB`);
  if (b.disk_total_gb != null) set("b-disk", `${b.disk_used_gb} / ${b.disk_total_gb} GB`);
  renderOsUpdates(snap.os_updates);
  renderInstallJob(snap.install_job);

  const pj = snap.provision_job, provEl = document.getElementById("as-prov");
  if (provEl) {
    if (pj && pj.state === "running") {
      provEl.hidden = false;
      provEl.textContent = `⏳ Provisioning ${pj.key || ""}: ${pj.step || "working"}…`;
    } else if (pj && (pj.state === "done" || pj.state === "failed")) {
      provEl.hidden = false;
      provEl.textContent = (pj.state === "done" ? "✓ " : "✗ ") + (pj.message || "");
    } else { provEl.hidden = true; }
  }
  stamp(snap.ts);
}

// Host OS (apt) update tile. GameDash keeps its own package lists, so a
// count here is genuinely fresh rather than however stale the system's
// /var/lib/apt/lists happens to be — the tooltip states when we last looked.
function renderOsUpdates(u) {
  const val = document.getElementById("b-os");
  const label = document.getElementById("b-os-label");
  const stat = document.getElementById("b-os-stat");
  if (!val || !label || !stat) return;

  const rel = (ts) => {
    if (!ts) return "never";
    const m = Math.max(0, (Date.now() / 1000 - ts) / 60);
    if (m < 1) return "just now";
    if (m < 60) return `${Math.round(m)}m ago`;
    if (m < 48 * 60) return `${Math.round(m / 60)}h ago`;
    return `${Math.round(m / 1440)}d ago`;
  };

  let text, sub, cls = "", tip;
  if (!u || (!u.checked_ts && !u.error)) {
    text = u && u.checking ? "checking…" : "…";
    sub = "OS updates";
    tip = "Checking the host OS for pending apt updates…";
  } else if (!u.ok) {
    text = "n/a";
    sub = "OS updates — check failed";
    cls = "warn";
    tip = `Could not check for OS updates: ${u.error || "unknown error"}`;
  } else if (u.count === 0) {
    text = "up to date";
    sub = `OS updates${u.reboot_required ? " · reboot required" : ""}`;
    cls = u.reboot_required ? "warn" : "ok";
    tip = `${u.os_name || "OS"} — no pending package updates.\nPackage lists refreshed ${rel(u.lists_ts)}.`;
  } else {
    text = String(u.count);
    sub = u.security_count
      ? `OS updates · ${u.security_count} security`
      : "OS updates";
    if (u.reboot_required) sub += " · reboot required";
    cls = u.security_count || u.reboot_required ? "bad" : "warn";
    const names = (u.packages || []).map((p) => `${p.name} ${p.current} → ${p.new}${p.security ? " (security)" : ""}`);
    if (u.truncated) names.push(`…and ${u.truncated} more`);
    tip = `${u.os_name || "OS"} — ${u.count} package(s) can be upgraded`
      + (u.security_count ? `, ${u.security_count} security` : "")
      + `.\nPackage lists refreshed ${rel(u.lists_ts)}.`
      + (u.reboot_required
          ? `\nA reboot is required${(u.reboot_packages || []).length ? ` (${u.reboot_packages.join(", ")})` : ""}.`
          : "")
      + `\n\n${names.join("\n")}`
      + `\n\nApply with:  sudo apt update && sudo apt upgrade`;
  }
  val.textContent = text;
  val.className = cls;
  label.textContent = sub;
  stat.title = tip;
}

async function checkUpdates() {
  const btn = document.getElementById("check-updates");
  if (btn) btn.disabled = true;
  try {
    const r = await api.post("/admin/updates/check");
    if (!r) return;
    const d = r.data;
    toast(d.ok ? "Checking for updates… (~30-60s; cards refresh when done)"
               : (d.error || "Update check failed."), !d.ok);
  } catch (e) { toast("Update check failed.", true); }
  finally { if (btn) btn.disabled = false; }
}

function wireUpdates() {
  const b = document.getElementById("check-updates");
  if (b && !b._wired) { b._wired = true; b.onclick = checkUpdates; }
}

// ---- Getting-started checklist ----
export async function loadChecklist() {
  const panel = document.getElementById("checklist-panel");
  if (!panel) return;
  let d = null;
  try {
    const r = await api.get("/admin/checklist");
    if (r && r.ok) d = r.data;
  } catch (e) { /* ignore */ }
  if (!d || !d.ok || d.hidden) { panel.hidden = true; return; }
  panel.hidden = false;
  panel.open = !d.all_done;
  const left = d.items.filter((i) => i.done === false && i.id !== "alerts").length;
  document.getElementById("checklist-sum").textContent = left ? `— ${left} step${left > 1 ? "s" : ""} to go` : "— all set";
  document.getElementById("checklist-list").innerHTML = d.items.map((i) => `
    <div class="check-row ${i.done ? "done" : ""}">
      <span class="mark">${i.done ? "✅" : (i.done === null ? "👉" : "⬜")}</span>
      <div><div class="c-title">${esc(i.title)}</div><div class="c-help">${esc(i.help)}</div></div>
      ${(!i.done && i.go) ? `<a class="ctl c-go" href="${esc(i.go)}" data-go="${esc(i.go)}">Do this</a>` : ""}
    </div>`).join("");
  if (!panel._wired) {
    panel._wired = true;
    panel.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-go]");
      if (!a || !a.dataset.go.startsWith("#")) return;     // other links navigate normally
      e.preventDefault();
      const target = document.querySelector(a.dataset.go);
      if (target) { target.open = true; target.scrollIntoView({ behavior: "smooth", block: "start" }); }
    });
    document.getElementById("checklist-hide").onclick = async () => {
      let r;
      try { r = await api.post("/admin/checklist", { hidden: true }); } catch (e) { r = null; }
      if (!r || !r.ok) { toast("Couldn't hide the checklist — try again.", true); return; }
      panel.hidden = true;
      toast("Checklist hidden.");
    };
  }
}

function wireControls() {
  const grid = document.getElementById("grid");
  if (!grid) return;
  grid.addEventListener("click", (e) => {
    const btn = e.target.closest("button.ctl");
    if (!btn) return;
    const card = btn.closest(".card[data-key]");
    if (!card) return;
    btn.disabled = true;
    Promise.resolve(doAction(card.dataset.key, btn.dataset.action, btn))
      .finally(() => { btn.disabled = false; });
  });
}

export function pollAdmin() {
  wireControls();
  wireJoin();
  wireUpdates();
  wireAddServer();
  loadGames();
  loadChecklist();
  poll(ADMIN_FEED, renderAdmin);
}
