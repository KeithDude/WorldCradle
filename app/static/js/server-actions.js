// What a server card's buttons do, and the windows some of them open: chat, "Can friends
// connect?", logs and the launch-script editor.
import { refreshAdminNow } from "./admin.js";
import { api, closeModal, esc, openModal, report, toast, withPlayerCheck } from "./core.js";

const postAction = (body) => api.post("/admin/action", body);

// the server's full name, from its card (for window titles and questions)
const cardName = (btn, key) => (btn && btn.closest(".card") && btn.closest(".card").dataset.name) || key;
const refreshSoon = (ms = 800) => setTimeout(refreshAdminNow, ms);

async function playerAction(key, btn, action) {
  if (!btn.dataset.target) { toast(`No player ID available to ${action}.`, true); return; }
  if (!confirm(`${action === "ban" ? "BAN" : "Kick"} ${btn.dataset.name || "this player"}?`)) return;
  const res = await postAction({ key, action, target: btn.dataset.target });
  if (res) { report(res, "Done.", "Failed."); refreshSoon(); }
}

// What the card buttons do. Anything not listed (start, stop, restart, save) is sent as it is.
const ACTIONS = {
  kick: (key, btn) => playerAction(key, btn, "kick"),
  ban: (key, btn) => playerAction(key, btn, "ban"),
  reach: (key) => openReach(key),
  chat: (key, btn) => openChat(key, cardName(btn, key)),
  logs: (key, btn) => openLogs(key, cardName(btn, key)),
  editscript: (key, btn) => openScriptEditor(key, cardName(btn, key)),
  async update(key, btn) {
    const gname = btn.dataset.gname || "this game";
    if (!confirm(`Update ${gname}?\n\nThis STOPS the server(s), runs the Steam update, then restarts — a few minutes of downtime (ARK can take longer).`)) return;
    const res = await withPlayerCheck(
      (confirmed) => api.post("/admin/updates/apply", { app: btn.dataset.app, confirm: confirmed }),
      `they'll be disconnected. Update ${gname} anyway?`);
    if (res) { report(res, "Update started.", "Update failed."); refreshSoon(1000); }
  },
  async removesrv(key, btn) {
    if (!confirm(`Remove server "${cardName(btn, key)}"?\n\nStops it and deletes its worldcradle unit. Save data on disk is left alone.`)) return;
    const res = await api.post("/admin/servers/remove", { key });
    if (res) { report(res, "Removed.", "Remove failed."); refreshSoon(); }
  },
  async kill(key, btn) {
    if (!confirm(`⚠ FORCE STOP "${cardName(btn, key)}" — NO SAVE\n\n` +
      `This stops the server IMMEDIATELY. Everything since the last ` +
      `autosave is LOST. Use this only if the server is frozen, or to intentionally ` +
      `discard recent changes (e.g. to roll back).\n\nForce stop without saving?`)) return;
    const res = await withPlayerCheck((confirmed) => postAction({ key, action: "kill", confirm: confirmed }),
      "they'll be disconnected with NO SAVE. Force stop anyway?");
    if (res) { report(res, "Force-stopped.", "Force stop failed."); refreshSoon(); }
  },
  async broadcast(key) {
    const message = prompt("Message to broadcast to players on this server:");
    if (!message) return;
    const res = await postAction({ key, action: "broadcast", message });
    if (res) report(res, "Sent.", "Couldn't send the message.");
  },
};

export async function doAction(key, action, btn) {
  if (ACTIONS[action]) { await ACTIONS[action](key, btn); return; }
  // stop and restart ask first if players are on
  const res = await withPlayerCheck((confirmed) => postAction({ key, action, confirm: confirmed }),
    `really ${action} this server?`);
  if (res) { report(res, "Done.", "Action failed."); refreshSoon(); }
}

// ---- live chat window (ARK) ----
const chat = { key: null, open: false };

function openChat(key, name) {
  chat.key = key;
  chat.open = true;
  const body = openModal({ id: "chat-modal", title: "Chat — " + name, size: "medium", flush: true,
    onClose: () => { chat.open = false; },
    bodyHtml: `<div class="chat-log" id="chat-log">
        <div class="chat-line muted">Listening for new chat… (only messages sent from now on appear)</div></div>
      <form class="chat-send">
        <input type="text" placeholder="Send a server message…" autocomplete="off">
        <button class="btn" type="submit">Send</button>
      </form>` });
  body.querySelector("form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = body.querySelector("input");
    const message = input.value.trim();
    if (!message) return;
    input.value = "";
    postAction({ key: chat.key, action: "broadcast", message });
  });
  pollChat();
}

function appendChat(text) {
  const log = document.getElementById("chat-log");
  if (!log) return;
  const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 30;
  text.split("\n").forEach((line) => {
    if (!line.trim()) return;
    const div = document.createElement("div");
    div.className = "chat-line";
    div.textContent = line;
    log.appendChild(div);
  });
  if (atBottom) log.scrollTop = log.scrollHeight;
}

async function pollChat() {
  if (!chat.open) return;
  const r = await postAction({ key: chat.key, action: "chat" });
  if (r && r.data && r.data.ok && r.data.chat) appendChat(r.data.chat);
  if (chat.open) setTimeout(pollChat, 4000);
}

// ---- "Can friends connect?" (router ports + reachability) ----
async function openReach(key) {
  const body = openModal({ id: "reach-modal", title: "Can friends connect?", size: "medium",
    bodyHtml: `<p class="muted">Checking… this takes a few seconds.</p>` });
  let d = null;
  try {
    const r = await api.get(`/admin/servers/reach?key=${encodeURIComponent(key)}`);
    if (!r) return;
    d = r.data;
  } catch (e) { /* handled below */ }
  if (!body.isConnected) return;   // closed while it was checking
  if (!d || !d.ok) { body.textContent = (d && d.error) || "The check couldn't be run. Try again in a moment."; return; }
  document.getElementById("reach-modal-title").textContent = "Can friends connect? — " + d.name;
  const verdict = {
    yes: d.evidence === "steam"
      ? `<p class="reach-v good">✅ <b>Looks good.</b> Steam's public server list shows this server at your address — a strong sign that people outside your home can find and join it. If a friend still can't get in, compare your router's rules with the list below.</p>`
      : `<p class="reach-v good">✅ <b>Yes.</b> The server answered on your public address, so the router is passing connections through to it.</p>`,
    stopped: `<p class="reach-v warn">⏸ <b>The server is stopped</b>, so there's nothing to test. Start it, give it a few minutes to finish loading, then check again.</p>`,
    unknown: d.evidence === "no-internet"
      ? `<p class="reach-v warn">❓ <b>Couldn't check.</b> This computer couldn't reach the internet to find your public address. Check its connection and try again.</p>`
      : `<p class="reach-v warn">❓ <b>We couldn't confirm it from here — that doesn't mean it's broken.</b> Most home routers won't let a computer test its own public address, and not every game appears in Steam's server list. The sure test: ask a friend to try joining, or test it yourself with your phone's <b>Mobile Hotspot</b> as described at the bottom.</p>`,
  }[d.verdict] || "";
  const rows = d.rules.map((r) =>
    `<tr><td><code>${esc(r.port)}</code></td><td>${esc(r.proto)}</td><td>${esc(r.what)}</td></tr>`).join("");
  body.innerHTML = `${verdict}
    ${d.join_address ? `<p>Friends connect to: <code>${esc(d.join_address)}</code></p>` : ""}
    <p><b>What your router needs.</b> For people outside your home to reach this server, your router has to pass these ports on to this computer${d.lan_ip ? ` (<code>${esc(d.lan_ip)}</code>)` : ""}. This is called <i>port forwarding</i>:</p>
    ${rows ? `<table class="reach-t"><tr><th>Port</th><th>Type</th><th>Used for</th></tr>${rows}</table>`
           : `<p class="muted">This server has no ports that need forwarding.</p>`}
    ${(d.keep_closed || []).length ? `<div class="reach-v bad">🔒 <b>Never forward these:</b> ${d.keep_closed.map((c) => `<code>${esc(c.port)}</code> (${esc(c.what)})`).join(", ")}. They control the server itself. WorldCradle uses them only from inside this computer; if they were reachable from the internet, a stranger could try to take the server over. Leave them out of your router — always.</div>` : ""}
    <ol class="join-steps">
      <li>Open your router's settings page${d.router_ip ? ` — usually by typing <code>${esc(d.router_ip)}</code> into a web browser's address bar` : ""}. The login is often printed on a sticker on the router.</li>
      <li>Find the section called <b>Port forwarding</b> (some routers call it <i>Virtual server</i>, <i>NAT</i> or <i>Applications &amp; gaming</i>).</li>
      <li>Add one rule for each row above: the same port number for “external” and “internal”, the type shown, and ${d.lan_ip ? `<code>${esc(d.lan_ip)}</code>` : "this computer's address"} as the device to send it to.</li>
      <li>Save, then press “Can friends connect?” again.</li>
    </ol>
    <p class="muted hint">📱 <b>Test it yourself from outside your home:</b> turn on your phone's <b>Mobile Hotspot</b>, connect a computer that has the game to that hotspot (not to your home Wi-Fi), and join using the “Friends connect to” address. That's exactly how a friend outside your home connects.</p>
    <p class="muted hint">If friends are only ever on your own home network, you don't need any of this — they can join using this computer's home address${d.lan_ip ? ` (<code>${esc(d.lan_ip)}</code>)` : ""}.</p>`;
}

// ---- per-server log viewer ----
const logs = { key: null };

function openLogs(key, name) {
  logs.key = key;
  openModal({ id: "logs-modal", title: "Logs — " + name, size: "wide", flush: true,
    headButtons: `<button class="ctl" id="logs-refresh">Refresh</button>`,
    bodyHtml: `<pre class="logs-body" id="logs-body">Loading…</pre>` });
  document.getElementById("logs-refresh").onclick = refreshLogs;
  refreshLogs();
}

async function refreshLogs() {
  const body = document.getElementById("logs-body");
  if (!body) return;
  try {
    const r = await api.get(`/admin/logs/${encodeURIComponent(logs.key)}?lines=400`);
    if (!r) return;
    const d = r.data;
    body.textContent = d.ok ? (d.text || "(empty)") : ("Error: " + (d.error || "failed"));
    body.scrollTop = body.scrollHeight;
  } catch (e) { body.textContent = "Failed to load logs."; }
}

// ---- launch-script editor ----
const script = { key: null };

async function openScriptEditor(key, name) {
  script.key = key;
  const body = openModal({ id: "script-modal", title: "Launch script — " + name, size: "wide", flush: true,
    headButtons: `<button class="ctl go" id="script-save">Save</button>`,
    bodyHtml: `<p class="muted script-path" id="script-path"></p>
      <textarea class="script-body" id="script-body" spellcheck="false" autocomplete="off" wrap="off" disabled>Loading…</textarea>
      <p class="muted script-note">Changes take effect on the next start/restart of this server.</p>` });
  document.getElementById("script-save").onclick = saveScript;
  const text = body.querySelector("textarea");
  try {
    const r = await api.get(`/admin/servers/script?key=${encodeURIComponent(key)}`);
    if (!r) return;
    if (r.data.ok) {
      text.value = r.data.content;
      text.disabled = false;
      body.querySelector("#script-path").textContent = r.data.path;
    } else {
      toast(r.data.error || "Can't edit this server's script.", true);
      closeModal("script-modal");
    }
  } catch (e) { toast("Failed to load script.", true); closeModal("script-modal"); }
}

async function saveScript() {
  const text = document.getElementById("script-body");
  if (!script.key || !text || text.disabled) return;
  try {
    const r = await api.post("/admin/servers/script", { key: script.key, content: text.value });
    if (!r) return;
    report(r, "Saved.", "Save failed.");
    if (r.data.ok) closeModal("script-modal");
  } catch (e) { toast("Save failed.", true); }
}
