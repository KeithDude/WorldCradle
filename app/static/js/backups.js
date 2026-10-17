// The Backups page: one section per server, with its backups and the buttons to make,
// restore, download and delete them.
import { api, esc, report, toast, withPlayerCheck } from "./core.js";

// ---- backups page (one section per server) ----
function bkRender(section, d) {
  const key = section.dataset.key;
  const info = section.querySelector(".bk-info");
  const list = section.querySelector(".bk-list");
  if (!d || !d.ok) { info.textContent = (d && d.error) || "Failed to load."; list.innerHTML = ""; return; }
  section.querySelector(".bk-keep").value = d.keep;
  const cw = section.querySelector(".bk-cluster-wrap");
  cw.hidden = !d.has_cluster;
  if (cw.hidden) section.querySelector(".bk-cluster").checked = false;
  section.querySelector('[data-bkact="create"]').disabled = !d.can_backup;
  info.innerHTML = d.can_backup
    ? `Save data: <code>${(d.save_paths || []).map(esc).join("</code>, <code>")}</code>`
    : "⚠ No save folder known for this server — nothing to back up. (Custom service: set a save folder.)";
  list.innerHTML = d.backups.length ? d.backups.map((b) => {
    const when = new Date(b.mtime * 1000).toLocaleString();
    return `<div class="bk-row">
      <span class="bk-meta"><b>${esc(when)}</b> · ${esc(b.size_h)} <span class="muted">${esc(b.name)}</span></span>
      <span class="bk-btns">
        <button class="ctl warn" data-bk="restore" data-name="${esc(b.name)}" title="Stop server, snapshot current save, then restore this backup">Restore</button>
        <a class="ctl" href="/admin/servers/backup-download?key=${encodeURIComponent(key)}&name=${encodeURIComponent(b.name)}">Download</a>
        <button class="ctl danger" data-bk="delete" data-name="${esc(b.name)}" title="Delete this backup file">Delete</button>
      </span></div>`;
  }).join("") : `<div class="muted">No backups yet.</div>`;
}

async function bkLoad(section) {
  let r;
  try { r = await api.get(`/admin/servers/backups?key=${encodeURIComponent(section.dataset.key)}`); }
  catch (e) { bkRender(section, { ok: false, error: "Couldn't reach the dashboard — try again in a moment." }); return; }
  if (r) bkRender(section, r.data);
}

async function bkCreate(section) {
  const btn = section.querySelector('[data-bkact="create"]'); btn.disabled = true;
  const r = await api.post("/admin/servers/backups", { key: section.dataset.key });
  if (r) toast(r.data.ok ? (r.data.message || "Backup created.") : (r.data.error || "Backup failed."), !r.data.ok);
  bkLoad(section);
}

async function bkSetKeep(section) {
  const r = await api.post("/admin/servers/backupkeep",
    { key: section.dataset.key, keep: Number(section.querySelector(".bk-keep").value) });
  if (r) { toast(r.data.ok ? (r.data.message || "Saved.") : (r.data.error || "Failed."), !r.data.ok); bkLoad(section); }
}

async function bkDelete(section, name) {
  if (!confirm(`Delete backup "${name}"? This can't be undone.`)) return;
  const r = await api.post("/admin/servers/backups/delete", { key: section.dataset.key, name });
  if (r) { toast(r.data.ok ? (r.data.message || "Deleted.") : (r.data.error || "Failed."), !r.data.ok); bkLoad(section); }
}

async function bkRestore(section, name) {
  const cw = section.querySelector(".bk-cluster-wrap");
  const incl = !cw.hidden && section.querySelector(".bk-cluster").checked;
  const scope = cw.hidden ? "" : (incl
    ? "\n\n⚠ Also overwriting the SHARED cluster — this affects ALL ARK maps."
    : "\n\n(Map save only — the shared cluster is left untouched.)");
  if (!confirm(`Restore "${name}"?\n\nThis STOPS the server, snapshots the current save, then overwrites it with this backup, and restarts. Progress since this backup will be replaced.${scope}`)) return;
  const body = { key: section.dataset.key, name, include_cluster: incl };
  const r = await withPlayerCheck(
    (confirmed) => api.post("/admin/servers/restore", { ...body, confirm: confirmed }),
    "they'll be disconnected by the restore. Proceed?");
  if (!r) return;
  report(r, "Restored.", "Restore failed.");
  bkLoad(section);
}

export function initBackupsPage() {
  const runAll = document.getElementById("bk-run-all");
  if (runAll) runAll.onclick = async () => {
    if (!confirm("Back up ALL servers now? This snapshots every server's save.")) return;
    runAll.disabled = true;
    const r = await api.post("/admin/backups/run-all", {});
    if (r) toast(r.data.ok ? (r.data.message || "Started.") : (r.data.error || "Failed."), !r.data.ok);
    setTimeout(() => { runAll.disabled = false; document.querySelectorAll(".bk-server").forEach(bkLoad); }, 8000);
  };
  document.querySelectorAll(".bk-server").forEach((section) => {
    section.addEventListener("click", (e) => {
      const act = e.target.closest("[data-bkact]");
      if (act) { if (act.dataset.bkact === "create") bkCreate(section); else bkSetKeep(section); return; }
      const b = e.target.closest("button[data-bk]");
      if (b) (b.dataset.bk === "restore" ? bkRestore : bkDelete)(section, b.dataset.name);
    });
    bkLoad(section);
  });
}
