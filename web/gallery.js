const $ = (id) => document.getElementById(id);
const grid = $("grid");
const statusEl = $("status");
let records = [];
let selectedId = null;

const thumbURL = (row) => `/ref_gallery/assets/thumb/${encodeURIComponent(row.id)}.webp`;
const fullURL = (row) => `/ref_gallery/assets/full/${encodeURIComponent(row.id)}.png`;

async function loadCatalog() {
  statusEl.textContent = "正在读取图库…";
  try {
    const res = await fetch("/ref_gallery/catalog", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "读取失败");
    records = data.records || [];
    const cats = [...new Set(records.map((r) => r.category).filter(Boolean))].sort();
    const filter = $("filter");
    filter.innerHTML = '<option value="all">全部分类</option>' +
      cats.map((c) => `<option value="${escapeHTML(c)}">${escapeHTML(c)}</option>`).join("");
    statusEl.textContent = records.length
      ? `共 ${records.length} 张图片。点击卡片选中，再点「使用选中图片」写回节点。`
      : "图库为空。上传图片或从文件夹导入后即可使用。";
    render();
  } catch (err) {
    statusEl.textContent = "读取图库失败：" + err.message;
  }
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function render() {
  const q = $("search").value.trim().toLowerCase();
  const cat = $("filter").value;
  const shown = records.filter((r) => {
    if (cat !== "all" && r.category !== cat) return false;
    if (!q) return true;
    const hay = [r.name, r.other_name, r.category, r.angle, (r.tags || []).join(" "), r.id]
      .join(" ").toLowerCase();
    return hay.includes(q);
  });
  grid.innerHTML = "";
  if (!shown.length) {
    grid.innerHTML = '<p class="empty">没有匹配的图片。</p>';
    return;
  }
  for (const row of shown) {
    const card = document.createElement("div");
    card.className = "card" + (row.id === selectedId ? " selected" : "");
    card.dataset.id = row.id;
    card.title = `${row.name}\n${row.category || ""} ${row.angle || ""}`;
    card.innerHTML = `<span class="pick"></span><img loading="lazy" alt="${escapeHTML(row.name)}" src="${thumbURL(row)}">
      <div class="meta"><div class="name">${escapeHTML(row.name)}</div>
      <div class="sub">${escapeHTML(row.category || "未分类")} · ${row.w}×${row.h}</div></div>`;
    card.addEventListener("click", () => {
      selectedId = row.id;
      document.querySelectorAll(".card").forEach((c) => c.classList.toggle("selected", c.dataset.id === selectedId));
      $("btn-delete").hidden = false;
    });
    card.addEventListener("dblclick", () => useSelected());
    grid.appendChild(card);
  }
}

function useSelected() {
  if (!selectedId) { statusEl.textContent = "请先点击一张图片选中。"; return; }
  const row = records.find((r) => r.id === selectedId);
  window.parent.postMessage({ type: "ref-gallery-select", id: selectedId, name: row?.name || "" }, location.origin);
}

$("search").addEventListener("input", render);
$("filter").addEventListener("change", render);
$("btn-select").addEventListener("click", useSelected);
$("btn-close").addEventListener("click", () =>
  window.parent.postMessage({ type: "ref-gallery-close" }, location.origin));

const uploadDialog = $("upload-dialog");
const importDialog = $("import-dialog");
let pickedFile = null, objectURL = null, ready = false;

$("btn-upload").addEventListener("click", () => uploadDialog.showModal());
$("upload-cancel").addEventListener("click", () => uploadDialog.close());
$("pick-file").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", () => {
  if (objectURL) URL.revokeObjectURL(objectURL);
  pickedFile = $("file").files[0] || null;
  ready = false;
  $("upload-save").disabled = true;
  $("upload-error").hidden = true;
  if (!pickedFile) { $("file-name").textContent = "尚未选择"; $("upload-preview").hidden = true; return; }
  $("file-name").textContent = `${pickedFile.name} (${(pickedFile.size / 1048576).toFixed(1)} MB)`;
  const img = $("upload-preview");
  objectURL = URL.createObjectURL(pickedFile);
  img.onload = () => {
    if (img.naturalWidth * img.naturalHeight > 32000000) {
      showUploadError("图片超过 3200 万像素限制。"); return;
    }
    ready = true; $("upload-save").disabled = false; img.hidden = false;
  };
  img.onerror = () => showUploadError("图片无法读取。");
  img.src = objectURL;
});

function showUploadError(msg) {
  $("upload-error").textContent = msg; $("upload-error").hidden = false;
  ready = false; $("upload-save").disabled = true;
}

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!ready || !pickedFile) { showUploadError("请选择一张图片。"); return; }
  if (!$("f-name").value.trim()) { showUploadError("请填写名称。"); return; }
  const form = new FormData();
  form.append("image", pickedFile);
  form.append("name", $("f-name").value.trim());
  form.append("other_name", $("f-other").value.trim());
  form.append("category", $("f-category").value.trim());
  form.append("angle", $("f-angle").value);
  form.append("tags", $("f-tags").value.trim());
  const btn = $("upload-save"); btn.disabled = true; btn.textContent = "保存中…";
  try {
    const res = await fetch("/ref_gallery/upload", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) { showUploadError(data.error || "上传失败"); return; }
    uploadDialog.close();
    $("upload-form").reset();
    $("file-name").textContent = "尚未选择";
    $("upload-preview").hidden = true;
    pickedFile = null; ready = false;
    selectedId = data.record.id;
    await loadCatalog();
    statusEl.textContent = `已保存「${data.record.name}」，已选中。点「使用选中图片」写回节点。`;
    window.parent.postMessage({ type: "ref-gallery-changed" }, location.origin);
  } catch (err) {
    showUploadError("上传失败：" + err.message);
  } finally {
    btn.textContent = "保存到图库"; btn.disabled = !ready;
  }
});

$("btn-import").addEventListener("click", () => { $("import-result").textContent = ""; importDialog.showModal(); });
$("import-cancel").addEventListener("click", () => importDialog.close());
$("import-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("import-save"); btn.disabled = true; btn.textContent = "导入中…";
  $("import-error").hidden = true;
  try {
    const res = await fetch("/ref_gallery/import_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: $("import-folder").value.trim(), category: $("import-category").value.trim() }),
    });
    const data = await res.json();
    if (!res.ok) { $("import-error").textContent = data.error || "导入失败"; $("import-error").hidden = false; return; }
    $("import-result").textContent = `导入 ${data.imported} 张，失败 ${data.failed.length} 张（共扫描 ${data.total} 张）。`;
    await loadCatalog();
    window.parent.postMessage({ type: "ref-gallery-changed" }, location.origin);
  } catch (err) {
    $("import-error").textContent = "导入失败：" + err.message; $("import-error").hidden = false;
  } finally {
    btn.textContent = "导入"; btn.disabled = false;
  }
});

$("btn-delete").addEventListener("click", async () => {
  if (!selectedId || !confirm("确定删除这张图片及其全部衍生文件？此操作不可撤销。")) return;
  try {
    const res = await fetch("/ref_gallery/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: selectedId }),
    });
    const data = await res.json();
    if (!res.ok) { statusEl.textContent = "删除失败：" + (data.error || "未知错误"); return; }
    selectedId = null; $("btn-delete").hidden = true;
    await loadCatalog();
    window.parent.postMessage({ type: "ref-gallery-changed" }, location.origin);
  } catch (err) { statusEl.textContent = "删除失败：" + err.message; }
});

window.addEventListener("message", (e) => {
  if (e.origin !== location.origin) return;
  if (e.data?.type === "ref-gallery-current" && typeof e.data.id === "string") {
    selectedId = e.data.id; render();
  }
});

window.parent.postMessage({ type: "ref-gallery-ready" }, location.origin);
loadCatalog();
