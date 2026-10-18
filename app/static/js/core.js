// What every page shares: escaping, talking to the dashboard, messages ("toasts"), pop-up
// windows and the players-online check. Nothing here touches the page when loaded.
const POLL_MS = 5000;

export const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// only ever link to plain https pages
export const safeUrl = (u) => typeof u === "string" && /^https:\/\/[^\s"'<>]+$/.test(u);

export const stamp = (ts) => {
  const el = document.getElementById("updated");
  if (el) el.textContent = "updated " + new Date((ts || Date.now() / 1000) * 1000).toLocaleTimeString();
};

// ---- pop-up windows ----
// Every window over the page is made here: a title bar with ✕ close, and it also closes on
// Escape or a click outside it. Returns the window's body element.
//   size: "" (narrow), "medium" or "wide";  flush: the body lays out its own padding
//   headButtons: extra buttons in the title bar;  onClose: called once it has closed
export function openModal({ id, title, bodyHtml = "", headButtons = "", size = "", flush = false, onClose }) {
  closeModal(id);
  const m = document.createElement("div");
  m.id = id;
  m.className = "modal";
  m.innerHTML = `<div class="modal-box ${size}" role="dialog" aria-modal="true" aria-labelledby="${id}-title">
      <div class="modal-head"><b id="${id}-title"></b>
        <span>${headButtons}<button class="linkbtn" data-close>✕ close</button></span></div>
      <div class="modal-body${flush ? " flush" : ""}">${bodyHtml}</div>
    </div>`;
  m.querySelector(`#${id}-title`).textContent = title;
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const close = () => {
    m.remove();
    document.removeEventListener("keydown", onKey);
    if (onClose) onClose();
  };
  m.addEventListener("click", (e) => { if (e.target === m || e.target.closest("[data-close]")) close(); });
  document.addEventListener("keydown", onKey);
  m.closeModal = close;
  document.body.appendChild(m);
  m.querySelector("[data-close]").focus();
  return m.querySelector(".modal-body");
}

export function closeModal(id) {
  const m = document.getElementById(id);
  if (m && m.closeModal) m.closeModal();
}

// ---- admin (full) ----
// A finished job's ✓/✗ message is shown for this long, then the box goes away (it used to stay
// for good, so a fresh page could show "Added …" from hours earlier). Measured against the
// snapshot's server time, so a computer whose clock is off doesn't matter.
const JOB_MESSAGE_SECONDS = 600;
export const recentlyFinished = (job, now) =>
  !!job && (job.state === "done" || job.state === "failed")
  && (!job.finished_ts || !now || now - job.finished_ts < JOB_MESSAGE_SECONDS);

export const pill = (cls, txt) => `<span class="pill ${cls}">${txt}</span>`;

export const reachPill = (v) => (v.reachable ? pill("on", "yes") : pill("bad", "no"));

const csrf = () => (document.querySelector('meta[name="csrf"]') || {}).content || "";

// ---- talking to the dashboard ----
// Every request goes through here. A change (POST) carries this page's CSRF token; a 401
// means the session ended, so it goes to the login page and returns null. Otherwise it
// returns {status, ok, data}. A network failure throws, for the caller's own message.
async function request(url, body) {
  const opts = { credentials: "same-origin" };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers = { "Content-Type": "application/json", "X-CSRF-Token": csrf() };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  if (r.status === 401) { location.href = "/login"; return null; }
  return { status: r.status, ok: r.ok, data: await r.json() };
}
export const api = { get: (url) => request(url), post: (url, body = {}) => request(url, body) };

export function fmtDur(s) {
  if (s == null) return "—";
  s = Math.floor(s);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
}

let toastTimer = null;
export function toast(msg, isError) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "toast" + (isError ? " err" : " ok");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 6000);
}

// Tell the owner how a request went: the server's own message, or a fallback.
export const report = (res, done, failed) =>
  toast(res.data.ok ? (res.data.message || done) : (res.data.error || failed), !res.data.ok);

// A change that would disconnect players is first sent without `confirm`. If anyone is on, the
// server answers 409 with who; the owner is asked, and only then is it sent again with
// confirm. `send(confirmed)` makes the request. Returns the final answer, or null.
export async function withPlayerCheck(send, question) {
  let res = await send(false);
  if (res && res.status === 409 && res.data.confirm_required && res.data.players != null) {
    const who = (res.data.names || []).length ? "\n\nOnline: " + res.data.names.join(", ") : "";
    if (!confirm(`⚠ ${res.data.players} player(s) ONLINE — ${question}${who}`)) {
      toast("Cancelled — players are online.", true);
      return null;
    }
    res = await send(true);
  }
  return res;
}

export async function poll(url, render) {
  try {
    const r = await api.get(url);
    if (!r) return;   // signed out: on the way to the login page
    render(r.data);
  } catch (e) { /* keep last good render */ }
  setTimeout(() => poll(url, render), POLL_MS);
}
