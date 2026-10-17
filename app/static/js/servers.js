// What the server cards on the public and admin pages share: the game headings, the server
// heading and player count, and the "How to join" window.
import { esc, openModal } from "./core.js";

// What every feed carries for the pages: the full game titles for the section headings, each
// game's "How to join" steps, and the address friends connect to. applyFeed() keeps it current.
const feed = { titles: {}, joinSteps: {}, publicHost: "" };

export function applyFeed(data) {
  if (data.public_host) feed.publicHost = data.public_host;
  if (data.titles) feed.titles = data.titles;
  if (data.join_steps) feed.joinSteps = data.join_steps;
}

// the proper title for a section heading ("ARK" → "ARK: Survival Evolved")
export const gameTitle = (g) => feed.titles[g] || g;
// the configured public address; else the address this page was opened at
const joinHost = () => feed.publicHost || location.hostname;

export const joinButton = (s) => s.join_port
  ? `<button class="joinbtn" data-kind="${esc(s.kind)}" data-name="${esc(s.name)}"
      data-srvname="${esc(s.server_name || "")}" data-port="${s.join_port}"
      title="Show step-by-step instructions + the address to connect to this server">ⓘ How to join</button>`
  : "";

// "How to join" steps come from each game type (GameType.join_steps); the values put into
// them are escaped here.
const PASSWORD_STEP = "Enter the join password (the one you were given — it's the same for every server).";

function joinSteps(kind, srvname, host, port) {
  const values = { address: esc(`${host}:${port}`), host: esc(host), port: esc(port),
                   server: esc(srvname || ""), password: PASSWORD_STEP };
  return (feed.joinSteps[kind] || ["Connect to <code>{address}</code>."])
    .map((step) => step.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m)));
}

function openJoin(info) {
  const addr = esc(`${joinHost()}:${info.port}`);
  const steps = joinSteps(info.kind, info.srvname, joinHost(), info.port).map((s) => `<li>${s}</li>`).join("");
  openModal({ id: "join-modal", title: "Join — " + info.name, bodyHtml: `
    ${info.srvname ? `<p class="join-srv">Server name: <b>${esc(info.srvname)}</b></p>` : ""}
    <p class="join-addr">Address: <code>${addr}</code></p>
    <ol class="join-steps">${steps}</ol>` });
}

export function wireJoin() {
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

// ---- card heading: the server's name, then Online / Offline ----
// (cards sit under their game's heading, so the game isn't repeated here)
const serverName = (v) => {
  if (v.server_name) return v.server_name;          // the name players see in the server list
  const i = v.name.indexOf(" · ");
  return i >= 0 ? v.name.slice(i + 3) : v.name;
};
export const cardHead = (v) => `<h2 title="The server's name, as players see it">🎮 ${esc(serverName(v))}</h2>
  <div class="state"><span class="dot ${v.online ? "on" : "off"}"></span>${v.online ? "Online" : "Offline"}</div>`;

// Rows depend only on the game (v.rows), never on whether it's running; a stopped server
// (or a number not known yet) shows a dash.
export const DASH = "—";
export const rows = (v) => v.rows || {};
export const playersBlock = (v) => {
  if (!rows(v).players) return "";
  const max = v.max_players ? ` / ${esc(v.max_players)}` : "";
  return `<div class="players">${v.players == null ? DASH : esc(v.players)}<span class="max">${max} players</span></div>`;
};
