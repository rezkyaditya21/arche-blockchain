/* ─── Config ──────────────────────────────────────────
   Set NODE_URL to your running ARCHE node HTTP API.
   If the explorer is served from the same machine as
   the node, use http://127.0.0.1:9334 (or whatever
   port you started the node with --http-port).
──────────────────────────────────────────────────── */
const NODE_URL  = "http://127.0.0.1:9334";  // node HTTP API
const EXPLORER_URL = "http://127.0.0.1:8080"; // explorer HTTP (rpc/explorer.py)
const REFRESH_MS = 5000;  // auto-refresh interval

const COIN = 100_000_000;
const toARC = v => (Number(v) / COIN).toFixed(8);
const short = (h, n = 16) => h ? h.slice(0, n) + "…" : "—";
const timeAgo = ts => {
  const d = Math.floor(Date.now() / 1000) - ts;
  if (d < 5)   return "just now";
  if (d < 60)  return d + "s ago";
  if (d < 3600) return Math.floor(d/60) + "m ago";
  return Math.floor(d/3600) + "h ago";
};
const fmtTime = ts => new Date(ts * 1000).toLocaleString();

// ─── State ──────────────────────────────────────────
let currentPage = 0;
const PER_PAGE = 20;
let chainHeight = 0;
let refreshTimer = null;

// ─── API helpers ────────────────────────────────────
async function apiFetch(url) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!r.ok) return null;
    return await r.json();
  } catch { return null; }
}

// Try node first, fall back to explorer
async function get(path) {
  const d = await apiFetch(NODE_URL + path);
  if (d !== null) return d;
  return apiFetch(EXPLORER_URL + path);
}

// ─── Bootstrap ──────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("searchBtn").addEventListener("click", doSearch);
  document.getElementById("searchInput").addEventListener("keydown", e => {
    if (e.key === "Enter") doSearch();
  });
  tick();
  refreshTimer = setInterval(tick, REFRESH_MS);
  footerClock();
});

async function tick() {
  await Promise.all([loadInfo(), loadBlocks(), loadMempool()]);
}

// ─── Info / stats ────────────────────────────────────
async function loadInfo() {
  // Try /info endpoint (explorer) first, fall back to /health (node)
  let info = await apiFetch(EXPLORER_URL + "/info");
  let health = await apiFetch(NODE_URL + "/health") || await apiFetch(EXPLORER_URL + "/health");

  const height = health?.height ?? info?.height ?? "—";
  const tip    = health?.tip    ?? info?.tip    ?? "";
  chainHeight  = typeof height === "number" ? height : 0;

  el("statHeight").textContent = height;
  el("statTip").textContent    = tip ? short(tip, 20) : "—";
  el("statTip").title          = tip;

  if (info) {
    el("statReward").textContent  = info.block_reward_arc + " ARC";
    el("statSupply").textContent  = Number(info.max_supply_arc).toLocaleString() + " ARC";
    const netName = info.ticker || "ARC";
    const badge = el("networkBadge");
    badge.textContent = netName.toLowerCase() === "arc" ? "testnet" : netName;
  }

  const peers = health?.peers?.length ?? "—";
  el("statPeers").textContent = peers;
}

// ─── Blocks table ───────────────────────────────────
async function loadBlocks() {
  const page = currentPage;
  const start = Math.max(0, chainHeight - (page + 1) * PER_PAGE + 1);
  const end   = Math.max(0, chainHeight - page * PER_PAGE);
  // Fetch via /chain?page=N endpoint
  const data = await apiFetch(
    `${EXPLORER_URL}/chain?page=${page}&per_page=${PER_PAGE}`
  );

  const tbody = el("blocksBody");
  if (!data || !data.blocks || data.blocks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading">No blocks found</td></tr>`;
    return;
  }

  const rows = [...data.blocks].reverse().map(b => {
    const hash  = b.hash || "";
    const bits  = b.bits ? "0x" + b.bits.toString(16) : "—";
    return `
      <tr onclick='showBlock(${b.index})'>
        <td class="height-link">${b.index}</td>
        <td class="hash" title="${hash}">${short(hash)}</td>
        <td>${timeAgo(b.timestamp)}</td>
        <td>${b.tx_count ?? "—"}</td>
        <td class="mono">${bits}</td>
      </tr>`;
  }).join("");

  tbody.innerHTML = rows;

  // Update total height from response
  if (typeof data.height === "number") {
    chainHeight = data.height;
    el("statHeight").textContent = chainHeight;
  }

  // Pagination controls
  const maxPage = Math.max(0, Math.ceil((chainHeight + 1) / PER_PAGE) - 1);
  el("pageInfo").textContent = `Page ${page + 1} of ${maxPage + 1}`;
  el("prevPage").disabled = page >= maxPage;
  el("nextPage").disabled = page <= 0;
}

function changePage(delta) {
  currentPage = Math.max(0, currentPage - delta);
  loadBlocks();
}

// ─── Mempool ────────────────────────────────────────
async function loadMempool() {
  const data = await get("/mempool");
  const tbody = el("mempoolBody");
  const txs = data?.mempool ?? [];

  el("statMempool").textContent = txs.length + " tx";

  if (txs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="loading">Mempool is empty</td></tr>`;
    return;
  }

  const rows = txs.slice(0, 50).map(tx => {
    const fee = estimateFee(tx);
    return `
      <tr onclick='showTx("${tx.txid}")'>
        <td class="hash" title="${tx.txid}">${short(tx.txid)}</td>
        <td>${(tx.inputs||[]).length}</td>
        <td>${(tx.outputs||[]).length}</td>
        <td class="green">${fee !== null ? toARC(fee) + " ARC" : "—"}</td>
      </tr>`;
  }).join("");

  tbody.innerHTML = rows;
}

function estimateFee(tx) {
  // Fee stored as _fee_cache on mempool tx dict
  if (typeof tx._fee_cache === "number") return tx._fee_cache;
  return null;
}

// ─── Search ─────────────────────────────────────────
async function doSearch() {
  const raw = el("searchInput").value.trim();
  if (!raw) return;

  // Detect type
  if (/^\d+$/.test(raw)) {
    // Block height
    await showBlock(parseInt(raw));
  } else if (/^[0-9a-fA-F]{64}$/.test(raw)) {
    // Could be txid or block hash
    const tx = await get(`/tx/${raw}`);
    if (tx && tx.txid) {
      showTxData(tx);
    } else {
      const bh = await get(`/block/hash/${raw}`);
      if (bh && typeof bh.index === "number") {
        await showBlock(bh.index);
      } else {
        showError(`Nothing found for: ${raw}`);
      }
    }
  } else if (/^[0-9a-fA-F]{40}$/.test(raw)) {
    // Address (hex)
    await showAddress(raw);
  } else if (/^A[1-9A-HJ-NP-Za-km-z]{25,40}$/.test(raw)) {
    // Base58 address — convert to hex via explorer
    const data = await get(`/balance/${raw}`);
    if (data) await showAddress(raw);
    else showError(`Address not found: ${raw}`);
  } else {
    showError(`Cannot determine type for: ${raw}`);
  }
}

// ─── Show Block ──────────────────────────────────────
async function showBlock(height) {
  const data = await get(`/block/${height}`);
  if (!data) { showError(`Block ${height} not found`); return; }

  const hash = data.hash || computeHashPlaceholder();
  const bits = data.bits ? "0x" + data.bits.toString(16) : "—";

  let txsHtml = (data.transactions || []).map(tx => renderTxCard(tx)).join("");

  setResult(`Block #${data.index}`, `
    <div class="result-section">
      <div class="kv-grid">
        <div class="kv-key">Height</div><div class="kv-val">${data.index}</div>
        <div class="kv-key">Hash</div><div class="kv-val mono">${data.hash || "—"}</div>
        <div class="kv-key">Prev Hash</div>
          <div class="kv-val mono">${data.prev_hash || "—"}</div>
        <div class="kv-key">Timestamp</div>
          <div class="kv-val">${fmtTime(data.timestamp)} (${timeAgo(data.timestamp)})</div>
        <div class="kv-key">Bits</div><div class="kv-val mono">${bits}</div>
        <div class="kv-key">Nonce</div><div class="kv-val mono">${data.nonce}</div>
        <div class="kv-key">Merkle Root</div>
          <div class="kv-val mono">${data.tx_merkle_root || "—"}</div>
        <div class="kv-key">Transactions</div>
          <div class="kv-val">${(data.transactions||[]).length}</div>
        <div class="kv-key">Version</div><div class="kv-val">${data.version}</div>
      </div>
    </div>
    <div class="result-section">
      <div class="panel-header" style="border:none;padding:0 0 .75rem 0">
        Transactions (${(data.transactions||[]).length})
      </div>
      ${txsHtml || '<p class="loading">No transactions</p>'}
    </div>
  `);
}

// ─── Show Tx ─────────────────────────────────────────
async function showTx(txid) {
  const data = await get(`/tx/${txid}`);
  if (!data) { showError(`Transaction not found: ${txid}`); return; }
  showTxData(data);
}

function showTxData(tx) {
  setResult(`Transaction`, `
    <div class="result-section">
      <div class="kv-grid">
        <div class="kv-key">Txid</div><div class="kv-val mono">${tx.txid}</div>
        <div class="kv-key">Type</div>
          <div class="kv-val">${tx.coinbase ? '<span class="yellow">Coinbase</span>' : 'Regular'}</div>
        <div class="kv-key">Inputs</div><div class="kv-val">${(tx.inputs||[]).length}</div>
        <div class="kv-key">Outputs</div><div class="kv-val">${(tx.outputs||[]).length}</div>
      </div>
    </div>
    <div class="result-section">${renderTxCard(tx, true)}</div>
  `);
}

// ─── Show Address ────────────────────────────────────
async function showAddress(addr) {
  const [balData, utxoData] = await Promise.all([
    get(`/balance/${addr}`),
    get(`/utxos/${addr}`),
  ]);

  const bal   = balData?.balance ?? 0;
  const balArc = balData?.balance_arc ?? toARC(bal);
  const utxos = utxoData?.utxos ?? [];

  const utxoRows = utxos.map(u => `
    <tr onclick='showTx("${u.txid}")'>
      <td class="hash" title="${u.txid}">${short(u.txid)}</td>
      <td>${u.index}</td>
      <td class="green">${toARC(u.value)} ARC</td>
    </tr>`).join("") || `<tr><td colspan="3" class="loading">No UTXOs</td></tr>`;

  setResult(`Address`, `
    <div class="result-section">
      <div class="kv-grid">
        <div class="kv-key">Address</div><div class="kv-val mono">${addr}</div>
        <div class="kv-key">Balance</div>
          <div class="kv-val green" style="font-size:1.1rem;font-weight:700">
            ${balArc} ARC
          </div>
        <div class="kv-key">UTXOs</div><div class="kv-val">${utxos.length}</div>
      </div>
    </div>
    <div class="result-section">
      <div class="panel-header" style="border:none;padding:0 0 .75rem 0">
        Unspent Outputs
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Txid</th><th>Index</th><th>Value</th></tr></thead>
          <tbody>${utxoRows}</tbody>
        </table>
      </div>
    </div>
  `);
}

// ─── Render tx card ──────────────────────────────────
function renderTxCard(tx, full = false) {
  const isCb = tx.coinbase;
  const inputs  = tx.inputs  || [];
  const outputs = tx.outputs || [];

  const inHtml = isCb
    ? `<div class="tx-io-row"><span class="yellow">Coinbase (new coins)</span></div>`
    : inputs.map(i =>
        `<div class="tx-io-row">
           <span class="tx-io-addr" onclick='showAddress("${i.pubkey_addr||""}")' title="${i.txid||""}">
             ${short(i.txid, 14)}:${i.index}
           </span>
         </div>`).join("") || "—";

  const outHtml = outputs.map(o =>
    `<div class="tx-io-row">
       <span class="tx-io-addr" onclick='showAddress("${o.address}")'
             title="${o.address}">${short(o.address, 14)}</span>
       <span class="tx-io-val">${toARC(o.value)} ARC</span>
     </div>`).join("") || "—";

  const totalOut = outputs.reduce((s, o) => s + (o.value || 0), 0);

  return `
    <div class="tx-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem">
        <span class="hash" onclick='showTx("${tx.txid}")' style="cursor:pointer;color:var(--accent2)"
              title="${tx.txid}">${short(tx.txid)}</span>
        <span class="green" style="font-weight:600">${toARC(totalOut)} ARC</span>
        ${isCb ? '<span class="badge badge-testnet" style="font-size:.65rem">coinbase</span>' : ""}
      </div>
      <div class="tx-flows">
        <div class="tx-side">
          <div class="tx-side-label">Inputs (${inputs.length || (isCb ? 0 : "?")})</div>
          ${inHtml}
        </div>
        <div class="tx-side">
          <div class="tx-side-label">Outputs (${outputs.length})</div>
          ${outHtml}
        </div>
      </div>
    </div>`;
}

// ─── Result panel helpers ─────────────────────────────
function setResult(title, html) {
  el("resultTitle").textContent = title;
  el("resultBody").innerHTML = html;
  el("resultPanel").classList.remove("hidden");
  el("resultPanel").scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeResult() {
  el("resultPanel").classList.add("hidden");
  el("searchInput").value = "";
}

function showError(msg) {
  setResult("Not Found", `
    <div class="result-section">
      <p class="red" style="padding:.5rem 0">${msg}</p>
    </div>`);
}

// ─── Footer clock ────────────────────────────────────
function footerClock() {
  const update = () => {
    el("footerTime").textContent = new Date().toLocaleTimeString();
  };
  update();
  setInterval(update, 1000);
}

// ─── Util ────────────────────────────────────────────
function el(id) { return document.getElementById(id); }
