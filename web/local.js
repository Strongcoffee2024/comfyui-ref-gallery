const $ = (id) => document.getElementById(id);
const grid = $("grid");
const statusEl = $("status");
let files = [];
let selectedPath = null;

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function thumbURL(path) {
  return `/ref_gallery/local_thumb?path=${encodeURIComponent(path)}`;
}

function render() {
  const q = $("search").value.trim().toLowerCase();
  const shown = files.filter((f) => !q || f.name.toLowerCase().includes(q) || f.rel.toLowerCase().includes(q));
  grid.innerHTML = "";
  $("btn-select").disabled = !selectedPath;
  if (!shown.length) {
    grid.innerHTML = `<p class="empty">${files.length ? "没有匹配的图片。" : "该文件夹没有找到图片（仅支持 PNG / JPEG / WebP / BMP）。"}</p>`;
    return;
  }
  for (const row of shown) {
    const card = document.createElement("div");
    card.className = "card" + (row.path === selectedPath ? " selected" : "");
    card.title = row.path;
    card.innerHTML = `<span class="pick"></span><img loading="lazy" alt="${escapeHTML(row.name)}" src="${thumbURL(row.path)}">
      <div class="meta"><div class="name" title="${escapeHTML(row.name)}">${escapeHTML(row.name)}</div>
      <div class="sub dim" title="${escapeHTML(row.rel)}">${escapeHTML(row.rel)} · ${(row.size / 1048576).toFixed(2)} MB</div></div>`;
    card.addEventListener("click", () => {
      selectedPath = row.path;
      document.querySelectorAll(".card").forEach((c) => c.classList.toggle("selected", c.title === selectedPath));
      $("btn-select").disabled = false;
    });
    card.addEventListener("dblclick", useSelected);
    grid.appendChild(card);
  }
}

async function listFolder() {
  const folder = $("folder").value.trim();
  if (!folder) { statusEl.textContent = "请先输入文件夹路径。"; return; }
  const btn = $("btn-list");
  btn.disabled = true; btn.textContent = "读取中…";
  statusEl.textContent = "正在读取文件夹…";
  try {
    const params = new URLSearchParams({ folder, recursive: $("recursive").checked ? "1" : "0" });
    const res = await fetch(`/ref_gallery/local_list?${params}`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "读取失败");
    files = data.files || [];
    selectedPath = null;
    statusEl.textContent = files.length
      ? `找到 ${files.length} 张图片${data.truncated ? "（已达上限 5000）" : ""}。点选后写回节点。`
      : "该文件夹没有找到图片。";
    render();
  } catch (err) {
    files = []; selectedPath = null; render();
    statusEl.textContent = "读取失败：" + err.message;
  } finally {
    btn.textContent = "列出图片"; btn.disabled = false;
  }
}

function useSelected() {
  if (!selectedPath) { statusEl.textContent = "请先点选一张图片。"; return; }
  window.parent.postMessage({ type: "ref-local-select", path: selectedPath }, location.origin);
}

$("btn-list").addEventListener("click", listFolder);
$("folder").addEventListener("keydown", (e) => { if (e.key === "Enter") listFolder(); });
$("search").addEventListener("input", render);
$("btn-select").addEventListener("click", useSelected);
$("btn-close").addEventListener("click", () =>
  window.parent.postMessage({ type: "ref-gallery-close" }, location.origin));

window.addEventListener("message", (e) => {
  if (e.origin !== location.origin) return;
  if (e.data?.type === "ref-local-current" && typeof e.data.path === "string") {
    $("folder").value = e.data.path;
  }
});

window.parent.postMessage({ type: "ref-local-ready" }, location.origin);
