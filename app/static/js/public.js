// The public page: every server's status and player count, and how to join.
import { esc, poll, stamp } from "./core.js";
import { applyFeed, cardHead, gameTitle, joinButton, playersBlock, wireJoin } from "./servers.js";

// ---- public (limited) ----
function renderPublic(data) {
  const grid = document.getElementById("grid");
  if (!grid) return;
  applyFeed(data);
  let lastGame = null;
  grid.innerHTML = data.servers.map((s) => {
    const game = s.name.split(" · ")[0];
    const head = game !== lastGame ? `<h3 class="group-head">${esc(gameTitle(game))}</h3>` : "";
    lastGame = game;
    return head + `
    <div class="card ${s.online ? "" : "off"}">
      ${joinButton(s)}
      ${cardHead(s)}
      ${playersBlock(s)}
    </div>`;
  }).join("");
  const oc = document.getElementById("online-count");
  if (oc) oc.textContent = data.servers.filter((s) => s.online).length;
  stamp(data.ts);
}

export function pollPublic() {
  wireJoin();
  poll("/api/public.json", renderPublic);
}
