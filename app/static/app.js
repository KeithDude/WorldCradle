/* gamedash front-end: polls JSON APIs and re-renders cards in place. */
const gamedash = (() => {
  const POLL_MS = 5000;

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // only ever link to plain https pages
  const safeUrl = (u) => typeof u === "string" && /^https:\/\/[^\s"'<>]+$/.test(u);

  const stamp = (ts) => {
    const el = document.getElementById("updated");
    if (el) el.textContent = "updated " + new Date((ts || Date.now() / 1000) * 1000).toLocaleTimeString();
  };

  // ---- join info (public + admin) ----
  // full game titles for the per-game section headers (cards keep the short
  // "ARK · Aberration" form; the group heading shows the proper title)
  // filled from each feed's `titles` (declared once, on the server's game types)
  let GAME_TITLES = {};
  const gameTitle = (g) => GAME_TITLES[g] || g;

  // configured public host; falls back to the host you're browsing from
  let PUBLIC_HOST = "";
  const joinHost = () => PUBLIC_HOST || location.hostname;

  const joinButton = (s) => s.join_port
    ? `<button class="joinbtn" data-kind="${esc(s.kind)}" data-name="${esc(s.name)}"
        data-srvname="${esc(s.server_name || "")}" data-port="${s.join_port}"
        title="Show step-by-step instructions + the address to connect to this server">ⓘ How to join</button>`
    : "";

  function joinSteps(kind, srvname, addr) {
    const pw = `Enter the join password (the one you were given — it's the same for every server).`;
    if (kind === "ark") return [
      `In Steam: <b>View → Game Servers → “Favorites” tab → “Add a Server”</b>.`,
      `Enter this address and add it: <code>${addr}</code>`,
      `Launch ARK and choose <b>“Join ARK”</b>.`,
      `Switch the session filter to <b>“Favorites”</b> — your added server shows up there.`,
      `Select <b>${esc(srvname)}</b> and join. ${pw}`,
    ];
    if (kind === "palworld") return [
      `In Palworld: <b>Join Multiplayer (Co-op) → Community Servers</b>, search <b>${esc(srvname)}</b>.`,
      `Or use <b>“Connect to Server”</b> by IP: <code>${addr}</code>`,
      pw,
    ];
    if (kind === "valheim") return [
      `In Valheim: <b>Start → “Join Game” tab → “Join IP”</b>.`,
      `Enter: <code>${addr}</code>`,
      pw,
    ];
    if (kind === "abiotic") return [
      `In Abiotic Factor: <b>Join a Game</b>, search the server list for <b>${esc(srvname)}</b>.`,
      `Or connect directly by IP: <code>${addr}</code>`,
      `${pw} Type it in the game's own password prompt — it can re-send a password remembered from another server.`,
    ];
    if (kind === "minecraft") return [
      `In Minecraft: Java Edition: <b>Multiplayer → Add Server</b>.`,
      `Server Address: <code>${addr}</code>`,
      `There is no password — the server owner has to add your Minecraft username to its whitelist first.`,
    ];
    if (kind === "dst") return [
      `In Don't Starve Together: <b>Browse Games</b>, search for <b>${esc(srvname)}</b> and join.`,
      `If it doesn't show up: open the console with the <b>~</b> key and type <code>c_connect("${addr.split(":")[0]}", ${addr.split(":")[1]}, "password")</code> with the join password.`,
      pw,
    ];
    if (kind === "satisfactory") return [
      `In Satisfactory: <b>Server Manager → “Add Server”</b>.`,
      `Enter: <code>${addr}</code>`,
      `Follow the prompts.`,
    ];
    return [`Connect to <code>${addr}</code>.`];
  }

  function ensureJoinModal() {
    let m = document.getElementById("join-modal");
    if (m) return m;
    m = document.createElement("div");
    m.id = "join-modal"; m.hidden = true;
    m.innerHTML = `
      <div class="join-box">
        <div class="join-head"><b id="join-title">How to join</b>
          <button class="linkbtn" id="join-close">✕ close</button></div>
        <div class="join-body" id="join-body"></div>
      </div>`;
    document.body.appendChild(m);
    m.querySelector("#join-close").onclick = () => { m.hidden = true; };
    m.addEventListener("click", (e) => { if (e.target === m) m.hidden = true; });
    return m;
  }

  function openJoin(info) {
    const m = ensureJoinModal();
    const addr = esc(`${joinHost()}:${info.port}`);   // goes into innerHTML via joinSteps
    document.getElementById("join-title").textContent = "Join — " + info.name;
    const steps = joinSteps(info.kind, info.srvname, addr)
      .map((s) => `<li>${s}</li>`).join("");
    document.getElementById("join-body").innerHTML = `
      ${info.srvname ? `<p class="join-srv">Server name: <b>${esc(info.srvname)}</b></p>` : ""}
      <p class="join-addr">Address: <code>${addr}</code></p>
      <ol class="join-steps">${steps}</ol>`;
    m.hidden = false;
  }

  function wireJoin() {
    const grid = document.getElementById("grid");
    if (!grid || grid._joinWired) return;
    grid._joinWired = true;
    grid.addEventListener("click", (e) => {
      const b = e.target.closest("button.joinbtn");
      if (!b) return;
      openJoin({ kind: b.dataset.kind, name: b.dataset.name,
                 srvname: b.dataset.srvname, port: b.dataset.port });
    });
  }

  const playersBlock = (v) => {
    if (v.players != null) {
      const max = v.max_players ? ` / ${esc(v.max_players)}` : "";
      return `<div class="players">${esc(v.players)}<span class="max">${max} players</span></div>`;
    }
    if (v.online) return `<div class="players unknown">online</div>`;
    return `<div class="statusline">offline</div>`;
  };

  // ---- public (limited) ----
  function renderPublic(data) {
    const grid = document.getElementById("grid");
    if (!grid) return;
    if (data.public_host) PUBLIC_HOST = data.public_host;
    if (data.titles) GAME_TITLES = data.titles;
    let lastGame = null;
    grid.innerHTML = data.servers.map((s) => {
      const game = s.name.split(" · ")[0];
      const head = game !== lastGame ? `<h3 class="group-head">${esc(gameTitle(game))}</h3>` : "";
      lastGame = game;
      return head + `
      <div class="card ${s.online ? "" : "off"}">
        ${joinButton(s)}
        <h2><span class="dot ${s.online ? "on" : "off"}"></span>${esc(s.name)}</h2>
        ${s.server_name ? `<div class="srvname">🎮 ${esc(s.server_name)}</div>` : ""}
        ${playersBlock(s)}
      </div>`;
    }).join("");
    const oc = document.getElementById("online-count");
    if (oc) oc.textContent = data.servers.filter((s) => s.online).length;
    stamp(data.ts);
  }

  // ---- admin (full) ----
  const pill = (cls, txt) => `<span class="pill ${cls}">${txt}</span>`;

  function reachPill(v) {
    // null = no query protocol to probe (Palworld/Valheim) → neutral, not alarming
    if (v.reachable == null) return `<span class="muted" title="no public query support; online status is via RCON/log">n/a</span>`;
    return v.reachable ? pill("on", "yes") : pill("bad", "no");
  }

  const csrf = () => (document.querySelector('meta[name="csrf"]') || {}).content || "";

  function fmtDur(s) {
    if (s == null) return "—";
    s = Math.floor(s);
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
  }

  let toastTimer = null;
  function toast(msg, isError) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast" + (isError ? " err" : " ok");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 6000);
  }

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
    const hasRcon = v.rcon_port != null;
    const btn = (action, label, cls) =>
      `<button class="ctl ${cls || ""}" data-action="${action}" title="${esc(ACTION_TITLES[action] || "")}">${label}</button>`;
    // lifecycle group: Start / Stop / Restart (+ Kill), with Remove after
    const life = v.online ? [btn("restart", "Restart", "warn"), btn("stop", "Stop", "danger"),
                             btn("kill", "Force stop", "danger")]
                          : [btn("start", "Start", "go")];
    if (v.managed === "gamedash") life.push(btn("removesrv", "Remove", "danger"));
    if (v.online && (hasRcon || v.kind === "satisfactory")) life.push(btn("save", "Save"));
    // action group (separated by a thin divider): message / chat / logs
    const editBtn = v.managed === "gamedash" ? btn("editscript", "Launch script") : "";
    const bkBtn = `<a class="ctl" href="/admin/backups#bk-${esc(v.key)}" title="${esc(ACTION_TITLES.backups)}">Backups</a>`;
    const acts = (v.online
      ? [hasRcon ? btn("broadcast", "Message") : "",
         v.kind === "ark" ? btn("chat", "Chat") : "",
         btn("logs", "Logs"), bkBtn, editBtn, btn("reach", "Can friends connect?")]
      : [btn("logs", "Logs"), bkBtn, editBtn, btn("reach", "Can friends connect?")]).filter(Boolean);
    const divider = acts.length ? '<span class="ctl-divider"></span>' : "";
    return `<div class="controls">${life.join("")}${divider}${acts.join("")}</div>`;
  }

  async function postAction(body) {
    const r = await fetch("/admin/action", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify(body),
    });
    if (r.status === 401) { location.href = "/login"; return null; }
    return { status: r.status, data: await r.json() };
  }

  async function doAction(key, action, btn) {
    // player-targeted actions
    if (action === "kick" || action === "ban") {
      const name = (btn && btn.dataset.name) || "this player";
      const target = btn && btn.dataset.target;
      if (!target) { toast("No player ID available to " + action + ".", true); return; }
      if (!confirm(`${action === "ban" ? "BAN" : "Kick"} ${name}?`)) return;
      const r = await postAction({ key, action, target });
      if (!r) return;
      if (r.data.ok) toast(r.data.message || "Done."); else toast(r.data.error || "Failed.", true);
      setTimeout(refreshAdminNow, 800);
      return;
    }
    if (action === "update") {
      const appId = btn.dataset.app;
      const gname = btn.dataset.gname || "this game";
      if (!confirm(`Update ${gname}?\n\nThis STOPS the server(s), runs the Steam update, then restarts — a few minutes of downtime (ARK can take longer).`)) return;
      const postUpd = async (body) => {
        const r = await fetch("/admin/updates/apply", {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
          body: JSON.stringify(body),
        });
        if (r.status === 401) { location.href = "/login"; return null; }
        return { status: r.status, data: await r.json() };
      };
      let res = await postUpd({ app: appId, confirm: false });
      if (!res) return;
      if (res.status === 409 && res.data.confirm_required) {
        const who = res.data.names && res.data.names.length ? "\n\nOnline: " + res.data.names.join(", ") : "";
        if (!confirm(`⚠ ${res.data.players} player(s) ONLINE — they'll be disconnected. Update ${gname} anyway?${who}`)) {
          toast("Cancelled — players online.", true); return;
        }
        res = await postUpd({ app: appId, confirm: true });
        if (!res) return;
      }
      toast(res.data.ok ? (res.data.message || "Update started.") : (res.data.error || "Update failed."), !res.data.ok);
      setTimeout(refreshAdminNow, 1000);
      return;
    }
    if (action === "removesrv") {
      const c = btn && btn.closest(".card");
      const nm = c && c.querySelector("h2") ? c.querySelector("h2").textContent.trim() : key;
      if (!confirm(`Remove server "${nm}"?\n\nStops it and deletes its gamedash unit. Save data on disk is left alone.`)) return;
      const r = await fetch("/admin/servers/remove", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ key }),
      });
      if (r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      toast(d.ok ? (d.message || "Removed.") : (d.error || "Remove failed."), !d.ok);
      setTimeout(refreshAdminNow, 800);
      return;
    }
    if (action === "reach") { openReach(key); return; }
    if (action === "chat" || action === "logs" || action === "editscript") {
      const c = btn && btn.closest(".card");
      const h = c && c.querySelector("h2");
      const name = h ? h.textContent.trim() : key;
      ({ chat: openChat, logs: openLogs, editscript: openScriptEditor }[action])(key, name);
      return;
    }

    if (action === "kill") {
      const card = btn && btn.closest(".card");
      const nm = (card && card.querySelector("h2")) ? card.querySelector("h2").textContent.trim() : key;
      if (!confirm(`⚠ KILL "${nm}" — NO SAVE\n\n` +
        `This force-kills the server process IMMEDIATELY. Everything since the last ` +
        `autosave is LOST, and the server stops. Use this only to intentionally ` +
        `discard recent changes (e.g. to roll back).\n\nForce-kill without saving?`)) return;
      let res = await postAction({ key, action: "kill", confirm: false });
      if (!res) return;
      if (res.status === 409 && res.data.confirm_required) {
        const who = res.data.names && res.data.names.length ? "\n\nOnline: " + res.data.names.join(", ") : "";
        if (!confirm(`⚠ ${res.data.players} player(s) ONLINE — they'll be disconnected with NO SAVE. Kill anyway?${who}`)) {
          toast("Cancelled — players online.", true); return;
        }
        res = await postAction({ key, action: "kill", confirm: true });
        if (!res) return;
      }
      toast(res.data.ok ? (res.data.message || "Killed.") : (res.data.error || "Kill failed."), !res.data.ok);
      setTimeout(refreshAdminNow, 800);
      return;
    }

    let message = "";
    if (action === "broadcast") {
      message = prompt("Message to broadcast to players on this server:");
      if (!message) return;
    }
    let res = await postAction({ key, action, message, confirm: false });
    if (!res) return;
    if (res.status === 409 && res.data.confirm_required) {
      const who = res.data.names && res.data.names.length
        ? "\n\nOnline: " + res.data.names.join(", ") : "";
      const ok = confirm(
        `⚠ ${res.data.players} player(s) are ONLINE.\n` +
        `Really ${action} this server?${who}`);
      if (!ok) { toast("Cancelled — players are online.", true); return; }
      res = await postAction({ key, action, message, confirm: true });
      if (!res) return;
    }
    if (res.data.ok) {
      toast(res.data.message || "Done.");
    } else {
      toast(res.data.error || "Action failed.", true);
    }
    setTimeout(refreshAdminNow, 800);  // reflect new state promptly
  }

  // ---- live chat panel (ARK GetChat) ----
  const chatState = { key: null, name: "", open: false };

  function ensureChatModal() {
    let m = document.getElementById("chat-modal");
    if (m) return m;
    m = document.createElement("div");
    m.id = "chat-modal";
    m.hidden = true;
    m.innerHTML = `
      <div class="chat-box">
        <div class="chat-head"><b id="chat-title">Chat</b>
          <button class="linkbtn" id="chat-close">✕ close</button></div>
        <div class="chat-log" id="chat-log"></div>
        <form class="chat-send" id="chat-send">
          <input type="text" id="chat-input" placeholder="Send a server message…" autocomplete="off">
          <button class="btn" type="submit">Send</button>
        </form>
      </div>`;
    document.body.appendChild(m);
    m.querySelector("#chat-close").onclick = closeChat;
    m.addEventListener("click", (e) => { if (e.target === m) closeChat(); });
    m.querySelector("#chat-send").addEventListener("submit", (e) => {
      e.preventDefault();
      const inp = document.getElementById("chat-input");
      const msg = inp.value.trim();
      if (!msg) return;
      inp.value = "";
      postAction({ key: chatState.key, action: "broadcast", message: msg });
    });
    return m;
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
    if (!chatState.open) return;
    const r = await postAction({ key: chatState.key, action: "chat" });
    if (r && r.data && r.data.ok && r.data.chat) appendChat(r.data.chat);
    if (chatState.open) setTimeout(pollChat, 4000);
  }

  function openChat(key, name) {
    const m = ensureChatModal();
    chatState.key = key; chatState.name = name; chatState.open = true;
    document.getElementById("chat-title").textContent = "Chat — " + name;
    document.getElementById("chat-log").innerHTML =
      '<div class="chat-line muted">Listening for new chat… (only messages sent from now on appear)</div>';
    m.hidden = false;
    pollChat();
  }

  function closeChat() {
    chatState.open = false;
    const m = document.getElementById("chat-modal");
    if (m) m.hidden = true;
  }

  // ---- "Can friends connect?" (router ports + reachability) ----
  async function openReach(key) {
    let m = document.getElementById("reach-modal");
    if (m) m.remove();
    m = document.createElement("div");
    m.id = "reach-modal";
    m.innerHTML = `<div class="join-box" role="dialog" aria-modal="true">
        <div class="join-head"><b id="reach-title">Can friends connect?</b>
          <button class="linkbtn" id="reach-close">✕ close</button></div>
        <div class="join-body" id="reach-body"><p class="muted">Checking… this takes a few seconds.</p></div>
      </div>`;
    document.body.appendChild(m);
    const close = () => m.remove();
    m.querySelector("#reach-close").onclick = close;
    m.addEventListener("click", (e) => { if (e.target === m) close(); });
    let d = null;
    try {
      const r = await fetch(`/admin/servers/reach?key=${encodeURIComponent(key)}`, { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; }
      d = await r.json();
    } catch (e) { /* handled below */ }
    const body = document.getElementById("reach-body");
    if (!body) return;
    if (!d || !d.ok) { body.textContent = (d && d.error) || "The check couldn't be run. Try again in a moment."; return; }
    document.getElementById("reach-title").textContent = "Can friends connect? — " + d.name;
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
      ${(d.keep_closed || []).length ? `<div class="reach-v bad">🔒 <b>Never forward these:</b> ${d.keep_closed.map((c) => `<code>${esc(c.port)}</code> (${esc(c.what)})`).join(", ")}. They control the server itself. GameDash uses them only from inside this computer; if they were reachable from the internet, a stranger could try to take the server over. Leave them out of your router — always.</div>` : ""}
      <ol class="join-steps">
        <li>Open your router's settings page${d.router_ip ? ` — usually by typing <code>${esc(d.router_ip)}</code> into a web browser's address bar` : ""}. The login is often printed on a sticker on the router.</li>
        <li>Find the section called <b>Port forwarding</b> (some routers call it <i>Virtual server</i>, <i>NAT</i> or <i>Applications &amp; gaming</i>).</li>
        <li>Add one rule for each row above: the same port number for “external” and “internal”, the type shown, and ${d.lan_ip ? `<code>${esc(d.lan_ip)}</code>` : "this computer's address"} as the device to send it to.</li>
        <li>Save, then press “Can friends connect?” again.</li>
      </ol>
      <p class="muted" style="font-size:.8rem">📱 <b>Test it yourself from outside your home:</b> turn on your phone's <b>Mobile Hotspot</b>, connect a computer that has the game to that hotspot (not to your home Wi-Fi), and join using the “Friends connect to” address. That's exactly how a friend outside your home connects.</p>
      <p class="muted" style="font-size:.8rem">If friends are only ever on your own home network, you don't need any of this — they can join using this computer's home address${d.lan_ip ? ` (<code>${esc(d.lan_ip)}</code>)` : ""}.</p>`;
  }

  // ---- per-server log viewer ----
  const logsState = { key: null };

  function ensureLogsModal() {
    let m = document.getElementById("logs-modal");
    if (m) return m;
    m = document.createElement("div");
    m.id = "logs-modal"; m.hidden = true;
    m.innerHTML = `
      <div class="logs-box">
        <div class="logs-head"><b id="logs-title">Logs</b>
          <span>
            <button class="ctl" id="logs-refresh">Refresh</button>
            <button class="linkbtn" id="logs-close">✕ close</button>
          </span></div>
        <pre class="logs-body" id="logs-body"></pre>
      </div>`;
    document.body.appendChild(m);
    m.querySelector("#logs-close").onclick = () => { m.hidden = true; };
    m.querySelector("#logs-refresh").onclick = refreshLogs;
    m.addEventListener("click", (e) => { if (e.target === m) m.hidden = true; });
    return m;
  }

  async function refreshLogs() {
    const body = document.getElementById("logs-body");
    if (!body) return;
    try {
      const r = await fetch(`/admin/logs/${encodeURIComponent(logsState.key)}?lines=400`,
                            { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      body.textContent = d.ok ? (d.text || "(empty)") : ("Error: " + (d.error || "failed"));
      body.scrollTop = body.scrollHeight;
    } catch (e) { body.textContent = "Failed to load logs."; }
  }

  function openLogs(key, name) {
    const m = ensureLogsModal();
    logsState.key = key;
    document.getElementById("logs-title").textContent = "Logs — " + name;
    document.getElementById("logs-body").textContent = "Loading…";
    m.hidden = false;
    refreshLogs();
  }

  // ---- launch-script editor ----
  const scriptState = { key: null };

  function ensureScriptModal() {
    let m = document.getElementById("script-modal");
    if (m) return m;
    m = document.createElement("div");
    m.id = "script-modal"; m.hidden = true;
    m.innerHTML = `
      <div class="logs-box">
        <div class="logs-head"><b id="script-title">Launch script</b>
          <span>
            <button class="ctl go" id="script-save">Save</button>
            <button class="linkbtn" id="script-close">✕ close</button>
          </span></div>
        <p class="muted" id="script-path" style="font-size:.75rem;margin:.2rem 0"></p>
        <textarea class="script-body" id="script-body" spellcheck="false" autocomplete="off" wrap="off"></textarea>
        <p class="muted" style="font-size:.75rem">Changes take effect on the next start/restart of this server.</p>
      </div>`;
    document.body.appendChild(m);
    m.querySelector("#script-close").onclick = () => { m.hidden = true; };
    m.querySelector("#script-save").onclick = saveScript;
    m.addEventListener("click", (e) => { if (e.target === m) m.hidden = true; });
    return m;
  }

  async function openScriptEditor(key, name) {
    const m = ensureScriptModal();
    scriptState.key = key;
    document.getElementById("script-title").textContent = "Launch script — " + name;
    document.getElementById("script-path").textContent = "";
    const body = document.getElementById("script-body");
    body.value = "Loading…"; body.disabled = true;
    m.hidden = false;
    try {
      const r = await fetch(`/admin/servers/script?key=${encodeURIComponent(key)}`,
                            { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      if (d.ok) {
        body.value = d.content; body.disabled = false;
        document.getElementById("script-path").textContent = d.path;
      } else {
        body.value = ""; body.disabled = true;
        toast(d.error || "Can't edit this server's script.", true);
        m.hidden = true;
      }
    } catch (e) { body.value = ""; toast("Failed to load script.", true); }
  }

  async function saveScript() {
    const body = document.getElementById("script-body");
    if (!scriptState.key || body.disabled) return;
    try {
      const r = await fetch("/admin/servers/script", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ key: scriptState.key, content: body.value }),
      });
      if (r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      toast(d.ok ? (d.message || "Saved.") : (d.error || "Save failed."), !d.ok);
      if (d.ok) document.getElementById("script-modal").hidden = true;
    } catch (e) { toast("Save failed.", true); }
  }

  // ---- shared POST helper ----
  async function postJSON(url, body) {
    const r = await fetch(url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify(body) });
    if (r.status === 401) { location.href = "/login"; return null; }
    return { status: r.status, data: await r.json() };
  }

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
    const r = await fetch(`/admin/servers/backups?key=${encodeURIComponent(section.dataset.key)}`,
                          { credentials: "same-origin" });
    if (r.status === 401) { location.href = "/login"; return; }
    bkRender(section, await r.json());
  }

  async function bkCreate(section) {
    const btn = section.querySelector('[data-bkact="create"]'); btn.disabled = true;
    const r = await postJSON("/admin/servers/backups", { key: section.dataset.key });
    if (r) toast(r.data.ok ? (r.data.message || "Backup created.") : (r.data.error || "Backup failed."), !r.data.ok);
    bkLoad(section);
  }

  async function bkSetKeep(section) {
    const r = await postJSON("/admin/servers/backupkeep",
      { key: section.dataset.key, keep: Number(section.querySelector(".bk-keep").value) });
    if (r) { toast(r.data.ok ? (r.data.message || "Saved.") : (r.data.error || "Failed."), !r.data.ok); bkLoad(section); }
  }

  async function bkDelete(section, name) {
    if (!confirm(`Delete backup "${name}"? This can't be undone.`)) return;
    const r = await postJSON("/admin/servers/backups/delete", { key: section.dataset.key, name });
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
    let r = await postJSON("/admin/servers/restore", { ...body, confirm: false });
    if (!r) return;
    if (r.status === 409 && r.data.confirm_required) {
      const who = r.data.names && r.data.names.length ? "\n\nOnline: " + r.data.names.join(", ") : "";
      if (!confirm(`⚠ ${r.data.players} player(s) ONLINE — they'll be disconnected by the restore. Proceed?${who}`)) {
        toast("Cancelled — players online.", true); return;
      }
      r = await postJSON("/admin/servers/restore", { ...body, confirm: true });
      if (!r) return;
    }
    toast(r.data.ok ? (r.data.message || "Restored.") : (r.data.error || "Restore failed."), !r.data.ok);
    bkLoad(section);
  }

  function initBackupsPage() {
    const runAll = document.getElementById("bk-run-all");
    if (runAll) runAll.onclick = async () => {
      if (!confirm("Back up ALL servers now? This snapshots every server's save.")) return;
      runAll.disabled = true;
      const r = await postJSON("/admin/backups/run-all", {});
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

  // ---- settings page ----
  async function loadGeneral() {
    if (!document.getElementById("gen-public-host")) return;
    let cfg = {};
    try { const r = await fetch("/admin/config", { credentials: "same-origin" }); if (r.ok) cfg = await r.json(); } catch (e) { /* ignore */ }
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
      const r = await postJSON("/admin/config", {
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
      const r = await postJSON("/admin/config", { default_backup_keep: Number(val("bk-default-keep")) });
      if (r) toast(r.data.ok ? "Saved." : (r.data.error || "Failed."), !r.data.ok);
    };
    const ra = document.getElementById("bk-run-all");
    if (ra) ra.onclick = async () => {
      if (!confirm("Back up ALL servers now?")) return;
      const r = await postJSON("/admin/backups/run-all", {});
      if (r) toast(r.data.ok ? (r.data.message || "Started.") : (r.data.error || "Failed."), !r.data.ok);
    };
  }

  async function loadPasswords() {
    const status = document.getElementById("pw-status");
    if (!status) return;
    try {
      const r = await fetch("/admin/passwords", { credentials: "same-origin" });
      if (r.ok) {
        const d = await r.json();
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
      const r = await postJSON("/admin/passwords", { join_password: join, admin_password: admin });
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

  function initSettings() { loadGeneral(); loadPasswords(); loadAlerts(); loadPortPool(); initCert(); }

  let adminUrl = "/api/admin.json";
  async function refreshAdminNow() {
    try {
      const r = await fetch(adminUrl, { credentials: "same-origin" });
      if (r.ok) renderAdmin(await r.json());
    } catch (e) { /* ignore */ }
  }

  function renderAdmin(snap) {
    const grid = document.getElementById("grid");
    if (!grid) return;
    if (snap.public_host) PUBLIC_HOST = snap.public_host;
    if (snap.titles) GAME_TITLES = snap.titles;
    let lastGame = null;
    grid.innerHTML = Object.values(snap.servers).map((v) => {
      const game = v.name.split(" · ")[0];
      const head = game !== lastGame ? `<h3 class="group-head">${esc(gameTitle(game))}</h3>` : "";
      lastGame = game;
      const kind = `<div class="kind-tag">${esc(v.kind)}${v.map_code ? " · " + esc(v.map_code) : ""}</div>`
        + (v.server_name ? `<div class="srvname">🎮 ${esc(v.server_name)}</div>` : "");
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
      const live = v.online ? `
        <dt title="Is the server answering on its port? “n/a” means this game can't be asked that way — it doesn't mean anything is wrong">answering</dt><dd>${reachPill(v)}</dd>
        <dt title="This server's share of the whole computer's processor (the same scale as Total CPU usage at the top), and the memory (RAM) used by all of its processes">CPU / RAM</dt><dd>${v.cpu_percent == null ? "…" : esc(v.cpu_percent) + "%"} · ${v.mem_mb == null ? "…" : esc(v.mem_mb >= 1024 ? (v.mem_mb / 1024).toFixed(1) + " GB" : v.mem_mb + " MB")}</dd>` : "";
      const sf = v.sf ? `
        <dt title="Server simulation rate — 30 is healthy; consistently lower means it's struggling">tick rate</dt><dd>${esc(v.sf.tick)}/30 ${v.sf.paused ? pill("warn", "paused") : ""}</dd>
        <dt title="Game progression (tech tier / project assembly phase)">progress</dt><dd>${v.sf.tier != null ? "Tier " + esc(v.sf.tier) : ""}${v.sf.phase != null ? " · Phase " + esc(v.sf.phase) : ""}</dd>
        <dt title="Total in-game time elapsed in this save">game time</dt><dd>${fmtDur(v.sf.uptime_s)}</dd>` : "";
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
      <div class="card ${v.online ? "" : "off"}" data-key="${esc(v.key)}">
        ${joinButton(v)}
        <h2><span class="dot ${v.online ? "on" : "off"}"></span>${esc(v.name)}</h2>
        ${kind}
        ${playersBlock(v)}
        ${names}
        ${note}
        <dl class="meta">
          <dt title="Whether the server is switched on">status</dt><dd>${v.online ? pill("on", "running") : pill("off", "stopped")}</dd>
          ${live}
          ${sf}
          <dt title="Does this server switch itself on when the computer starts up?">starts with computer</dt><dd>${v.enabled ? pill("on", "yes") : pill("off", "no")}</dd>
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

  async function poll(url, render) {
    try {
      const r = await fetch(url, { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; }
      render(await r.json());
    } catch (e) { /* keep last good render */ }
    setTimeout(() => poll(url, render), POLL_MS);
  }

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
        <span class="muted" style="font-size:.75rem;font-weight:normal">${tip}</span></label>`;
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
      }).join("") || `<p class="muted" style="font-size:.85rem">No alerts set up yet.</p>`;
    };
    const showResults = (results, target) => {
      const html = (results || []).map((r) => r.ok
        ? `<div class="note good">✅ ${esc(r.service)}: sent — check it arrived.</div>`
        : `<div class="note bad">❌ ${esc(r.service)}: ${esc(r.error)}</div>`).join("")
        || `<div class="note">Nothing to send to yet — add a place first.</div>`;
      document.getElementById(target).innerHTML = html;
    };
    try {
      const r = await fetch("/admin/alerts", { credentials: "same-origin" });
      if (!r.ok) return;
      const a = await r.json();
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
      const r = await fetch("/admin/alerts", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify(body),
      });
      const d = await r.json();
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
      const r = await fetch("/admin/portpool", { credentials: "same-origin" });
      if (r.ok) {
        const pool = (await r.json()).port_pool || {};
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
      const r = await fetch("/admin/portpool", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify(body),
      });
      if (r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      toast(d.ok ? "Port pool saved." : (d.error || "Save failed."), !d.ok);
    };
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
      const r = await fetch("/admin/updates/check", {
        method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf() },
      });
      if (r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      toast(d.ok ? "Checking for updates… (~30-60s; cards refresh when done)"
                 : (d.error || "Update check failed."), !d.ok);
    } catch (e) { toast("Update check failed.", true); }
    finally { if (btn) btn.disabled = false; }
  }

  function wireUpdates() {
    const b = document.getElementById("check-updates");
    if (b && !b._wired) { b._wired = true; b.onclick = checkUpdates; }
  }

  // ---- Settings: trusted certificate (Let's Encrypt) ----
  async function initCert() {
    const status = document.getElementById("cert-status");
    if (!status) return;
    const get = async () => {
      try {
        const r = await fetch("/admin/cert", { credentials: "same-origin" });
        return r.ok ? await r.json() : null;
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
      if (!d.available) { job.hidden = false; job.textContent = "The certificate tool isn't installed yet — run the GameDash installer again to add it."; }
      else if (j.state === "running") { job.hidden = false; job.textContent = `⏳ ${j.step || "Working"}…`; }
      else if (j.state === "done" || j.state === "failed") { job.hidden = false; job.textContent = (j.state === "done" ? "✅ " : "✗ ") + (j.message || ""); }
      else job.hidden = true;
      return j.state === "running";
    };
    const watch = async () => { if (show(await get())) setTimeout(watch, 2500); };
    watch();
    document.getElementById("cert-go").onclick = async () => {
      const r = await fetch("/admin/cert", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ domain: document.getElementById("cert-domain").value,
                               email: document.getElementById("cert-email").value,
                               agree: document.getElementById("cert-agree").checked }),
      });
      if (r.status === 401) { location.href = "/login"; return; }
      const d = await r.json();
      toast(d.ok ? d.message : (d.error || "Couldn't start the request."), !d.ok);
      if (d.ok) watch();
    };
  }

  // ---- Getting-started checklist ----
  async function loadChecklist() {
    const panel = document.getElementById("checklist-panel");
    if (!panel) return;
    let d = null;
    try {
      const r = await fetch("/admin/checklist", { credentials: "same-origin" });
      if (r.ok) d = await r.json();
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
        await fetch("/admin/checklist", {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
          body: JSON.stringify({ hidden: true }),
        });
        panel.hidden = true;
        toast("Checklist hidden.");
      };
    }
  }

  // ---- Games panel: what's installed, and install the rest ----
  const gamesState = { lastJob: "", wired: false };

  async function loadGames() {
    const list = document.getElementById("games-list");
    if (!list) return;
    let d = null;
    try {
      const r = await fetch("/admin/games", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; }
      d = await r.json();
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
        ? pill("on", "installed") + `<button class="linkbtn" data-uninstall="${esc(g.kind)}" data-label="${esc(g.label)}" style="font-size:.75rem">Uninstall</button>`
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
          const r = await fetch("/admin/games/uninstall", {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
            body: JSON.stringify({ kind: u.dataset.uninstall }),
          });
          if (r.status === 401) { location.href = "/login"; return; }
          const res = await r.json();
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
          const r = await fetch("/admin/games/install", {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
            body: JSON.stringify({ kind: b.dataset.install }),
          });
          if (r.status === 401) { location.href = "/login"; return; }
          const res = await r.json();
          toast(res.ok ? res.message : (res.error || "Couldn't start the install."), !res.ok);
          if (res.ok) { refreshAdminNow(); loadGames(); } else { b.disabled = false; }
        } catch (err) { toast("Couldn't start the install.", true); b.disabled = false; }
      });
    }
  }

  // called on every admin poll with the install job's state
  function renderInstallJob(job) {
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

  async function wireAddServer() {
    const b = document.getElementById("as-submit");
    if (!b || b._wired) return;
    b._wired = true;
    const kindSel = document.getElementById("as-kind");
    let types = [];
    try {
      const r = await fetch("/admin/servers/types", { credentials: "same-origin" });
      if (r.ok) types = (await r.json()).types || [];
    } catch (e) { /* ignore */ }
    const keep = kindSel.value;   // re-wired after an install finishes: keep the selection
    kindSel.innerHTML = types.map((t) => `<option value="${esc(t.kind)}">${esc(t.label)}${t.installed === false ? " — not installed yet" : ""}</option>`).join("");
    if (keep && types.some((t) => t.kind === keep)) kindSel.value = keep;

    // Is a port pool configured? Gate the "use port pool" checkbox on it.
    let poolReady = false;
    try {
      const pr = await fetch("/admin/portpool", { credentials: "same-origin" });
      if (pr.ok) poolReady = Object.keys((await pr.json()).port_pool || {}).length > 0;
    } catch (e) { /* ignore */ }
    const poolCk = document.getElementById("as-pool");
    const poolNote = document.getElementById("as-pool-note");
    poolCk.disabled = !poolReady;
    if (!poolReady) poolCk.checked = false;
    poolNote.textContent = poolReady ? "(allocate ports from the pool)" : "(no pool configured)";
    document.getElementById("as-pool-wrap").style.display = poolReady ? "" : "none";   // nothing to offer without a pool

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
        if (el) { el.disabled = on; el.style.opacity = on ? .5 : 1; }
      });
    };
    poolCk.onchange = syncPortBoxes;
    const render = () => {
      const t = types.find((x) => x.kind === kindSel.value) || { custom: true, extra_fields: [] };
      document.getElementById("as-custom").style.display = t.custom ? "" : "none";
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
    const confirmSharedPorts = (newName, conflicts) => new Promise((resolve) => {
      let m = document.getElementById("ports-modal");
      if (m) m.remove();
      m = document.createElement("div");
      m.id = "ports-modal";
      const others = [...new Set(conflicts.flatMap((c) => c.servers))];
      const who = others.map((n) => `<b>${esc(n)}</b>`).join(", ");
      const rows = conflicts.map((c) =>
        `<li>${esc(c.label)} <code>${esc(c.port)}</code> — assigned to ${c.servers.map((n) => `<b>${esc(n)}</b>`).join(", ")}</li>`).join("");
      m.innerHTML = `
        <div class="join-box" role="dialog" aria-modal="true" aria-labelledby="ports-title">
          <div class="join-head"><b id="ports-title">⚠ These ports are already assigned</b></div>
          <div class="join-body">
            <p>${conflicts.length > 1 ? "Some of the ports" : "A port"} you entered for <b>${esc(newName || "this server")}</b>
              ${conflicts.length > 1 ? "are" : "is"} already assigned to another server on this dashboard:</p>
            <ul class="ports-list">${rows}</ul>
            <p>Two servers cannot listen on the same port at the same time. If you continue, the new server
              and ${who} will share these ports, which means:</p>
            <ul>
              <li><b>Only one of them can run at a time.</b> The dashboard will refuse to start one while
                another is running — stop the running server first, then start the other.</li>
              <li>The new server is created but <b>not started</b> if one of the others is running now.</li>
              <li>Set only one of them to start at boot. If more than one starts automatically, whichever
                starts first takes the ports and the rest will fail to start.</li>
              <li>Your router's forwarding for these ports serves whichever server is currently running.</li>
            </ul>
            <p>This is the right setup when you intend to swap between servers on one set of forwarded
              ports. If that is not what you want, go back and enter different ports — or leave the port
              boxes blank and free ports will be chosen for you.</p>
          </div>
          <div class="ports-actions">
            <button class="ctl" id="ports-back">Go back and change ports</button>
            <button class="ctl warn" id="ports-go">Continue with shared ports</button>
          </div>
        </div>`;
      document.body.appendChild(m);
      const done = (v) => { m.remove(); document.removeEventListener("keydown", onKey); resolve(v); };
      const onKey = (e) => { if (e.key === "Escape") done(false); };
      document.addEventListener("keydown", onKey);
      m.querySelector("#ports-back").onclick = () => done(false);
      m.querySelector("#ports-go").onclick = () => done(true);
      m.addEventListener("click", (e) => { if (e.target === m) done(false); });
      m.querySelector("#ports-back").focus();   // the safe choice is the default
    });

    const postAdd = async (spec) => {
      const r = await fetch("/admin/servers/add", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify(spec),
      });
      if (r.status === 401) { location.href = "/login"; return null; }
      return { status: r.status, data: await r.json() };
    };
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
        // a typed port that another server already uses → explain, then share on request
        if (res.status === 409 && res.data.confirm_required && res.data.port_conflict) {
          if (!(await confirmSharedPorts(spec.name, res.data.port_conflict))) {
            toast("Nothing was created — change the ports and try again.", true); return;
          }
          spec.share_ports = true;
          res = await postAdd(spec);
          if (!res) return;
        }
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

  return {
    pollPublic: () => { wireJoin(); poll("/api/public.json", renderPublic); },
    pollAdmin: () => { wireControls(); wireJoin(); wireUpdates(); wireAddServer(); loadGames(); loadChecklist(); poll("/api/admin.json", renderAdmin); },
    initSettings,
    initBackupsPage,
  };
})();
