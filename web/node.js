import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function previewURL(id) {
  return api.apiURL(`/ref_gallery/assets/preview/${encodeURIComponent(id)}.webp`);
}

function localPreviewURL(path) {
  return api.apiURL(`/ref_gallery/local_thumb?path=${encodeURIComponent(path)}`);
}

function wireGalleryNode(nodeType, nodeData) {
  const created = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function () {
    created?.apply(this, arguments);
    const node = this;
    const isRandom = nodeData.name === "RandomRefGallery";
    const idWidget = node.widgets.find((w) => w.name === "image_id");
    const localWidget = node.widgets.find((w) => w.name === "local_path");
    if (!idWidget || !localWidget) return;

    let dialog = null, frame = null;

    const previewBox = document.createElement("div");
    previewBox.style.cssText = "position:relative;width:100%;height:100%;min-height:280px;max-height:460px;contain:size;box-sizing:border-box;background:#f4f3ef;border-radius:8px;overflow:hidden;";
    const preview = document.createElement("img");
    preview.style.cssText = "display:block;position:absolute;inset:0;width:100%;height:100%;object-fit:contain;";
    preview.alt = "参考图预览";
    const previewMsg = document.createElement("div");
    previewMsg.style.cssText = "display:none;position:absolute;inset:12px;place-items:center;color:#8b2e2e;font:13px/1.6 sans-serif;text-align:center;overflow-wrap:anywhere;";
    previewBox.append(preview, previewMsg);

    const pickedStrip = document.createElement("div");
    pickedStrip.style.cssText = "display:none;position:absolute;left:0;right:0;bottom:0;gap:6px;padding:6px;overflow-x:auto;background:rgba(244,243,239,.92);border-top:1px solid #d9d7d0;";
    previewBox.append(pickedStrip);

    let request = 0;
    function updatePreview() {
      const token = ++request;
      const local = String(localWidget.value || "").trim();
      const id = String(idWidget.value || "");
      previewMsg.style.display = "none"; preview.style.display = "block";
      if (!local && !id) {
        preview.removeAttribute("src");
        previewMsg.textContent = "尚未选图。点「浏览参考图库」，或点「从电脑选择图片」。";
        previewMsg.style.display = "grid"; preview.style.display = "none";
        return;
      }
      preview.onload = () => { if (token === request) { preview.style.display = "block"; previewMsg.style.display = "none"; } };
      preview.onerror = () => { if (token === request) { preview.style.display = "none"; previewMsg.textContent = "预览加载失败，图片可能已被移动或删除。"; previewMsg.style.display = "grid"; } };
      preview.src = local ? localPreviewURL(local) : previewURL(id);
    }

    const pickedPaths = [];
    function renderPickedStrip() {
      pickedStrip.innerHTML = "";
      if (pickedPaths.length < 2) { pickedStrip.style.display = "none"; return; }
      pickedStrip.style.display = "flex";
      for (const p of pickedPaths) {
        const t = document.createElement("img");
        t.src = localPreviewURL(p);
        t.title = p;
        t.style.cssText = "width:56px;height:64px;object-fit:cover;border:2px solid transparent;border-radius:5px;cursor:pointer;flex:0 0 auto;background:#fff;";
        if (p === String(localWidget.value || "").trim()) t.style.borderColor = "#2f6b57";
        t.onclick = () => {
          localWidget.value = p;
          idWidget.value = "";
          localWidget.callback?.(localWidget.value);
          idWidget.callback?.(idWidget.value);
          node.setDirtyCanvas(true, true);
          app.graph.change();
          renderPickedStrip();
        };
        pickedStrip.append(t);
      }
    }

    for (const widget of [idWidget, localWidget]) {
      const cb = widget.callback;
      widget.callback = function () { cb?.apply(this, arguments); updatePreview(); };
    }

    function receive(e) {
      if (e.origin !== location.origin || e.source !== frame?.contentWindow) return;
      const data = e.data || {};
      if (data.type === "ref-gallery-ready") {
        frame.contentWindow.postMessage({ type: "ref-gallery-current", id: String(idWidget.value || "") }, location.origin);
      }
      if (data.type === "ref-gallery-changed") { updatePreview(); }
      if (data.type === "ref-gallery-close") { close(); return; }
      if (data.type === "ref-gallery-select" && typeof data.id === "string") {
        idWidget.value = data.id;
        localWidget.value = "";
        idWidget.callback?.(idWidget.value);
        localWidget.callback?.(localWidget.value);
        if (isRandom) {
          const lock = node.widgets.find((w) => w.name === "locked");
          if (lock) { lock.value = true; lock.callback?.(true); }
        }
        node.setDirtyCanvas(true, true);
        app.graph.change();
        close();
      }
    }

    function close() {
      window.removeEventListener("message", receive);
      dialog?.remove(); dialog = null; frame = null;
    }

    function openGallery() {
      if (dialog) return;
      dialog = document.createElement("dialog");
      dialog.style.cssText = "width:96vw;height:94vh;max-width:1800px;padding:0;border:1px solid #777;border-radius:12px;background:#f7f7f5;";
      const header = document.createElement("div");
      header.style.cssText = "height:44px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;background:#e9f0eb;color:#244133;font:14px sans-serif;";
      const title = document.createElement("strong");
      title.textContent = "参考图库 · 选一张图片后点「使用选中图片」";
      const x = document.createElement("button");
      x.textContent = "关闭"; x.style.cssText = "cursor:pointer;padding:5px 14px;border-radius:6px;border:1px solid #b9c9bf;background:#fff;";
      x.onclick = close; header.append(title, x);
      frame = document.createElement("iframe");
      frame.src = api.apiURL("/ref_gallery/gallery");
      frame.title = "参考图库";
      frame.style.cssText = "width:100%;height:calc(100% - 44px);border:0;";
      dialog.append(header, frame);
      window.addEventListener("message", receive);
      dialog.addEventListener("cancel", (ev) => { ev.preventDefault(); close(); });
      dialog.addEventListener("click", (ev) => { if (ev.target === dialog) close(); });
      document.body.append(dialog); dialog.showModal();
    }

    const browseGallery = document.createElement("button");
    browseGallery.type = "button";
    browseGallery.textContent = "浏览参考图库 · 上传 / 搜索 / 选图";
    browseGallery.style.cssText = "width:100%;height:36px;border:1px solid #b9c9bf;border-radius:6px;background:#e9f0eb;color:#244133;cursor:pointer;font:12px sans-serif;";
    browseGallery.onclick = openGallery;

    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/png,image/jpeg,image/webp,image/bmp";
    fileInput.multiple = true;
    fileInput.style.display = "none";
    document.body.append(fileInput);

    const pickLocal = document.createElement("button");
    pickLocal.type = "button";
    pickLocal.textContent = "从电脑选择图片（像 Load Image）";
    pickLocal.style.cssText = "width:100%;height:36px;border:1px solid #b9c9bf;border-radius:6px;background:#fff;color:#244133;cursor:pointer;font:12px sans-serif;";
    pickLocal.onclick = () => { fileInput.value = ""; fileInput.click(); };

    fileInput.addEventListener("change", async () => {
      const files = Array.from(fileInput.files || []);
      if (!files.length) return;
      const old = pickLocal.textContent;
      pickLocal.disabled = true;
      pickLocal.textContent = `上传中… 0/${files.length}`;
      let done = 0;
      const paths = [];
      for (const file of files) {
        try {
          const form = new FormData();
          form.append("image", file, file.name);
          const res = await fetch(api.apiURL("/ref_gallery/pick"), { method: "POST", body: form });
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || "上传失败");
          paths.push(data.path);
        } catch (err) {
          pickLocal.textContent = "上传失败：" + err.message;
          setTimeout(() => { pickLocal.textContent = old; pickLocal.disabled = false; }, 2500);
          return;
        }
        done += 1;
        pickLocal.textContent = `上传中… ${done}/${files.length}`;
      }
      pickedPaths.length = 0;
      pickedPaths.push(...paths);
      if (paths.length) {
        localWidget.value = paths[0];
        idWidget.value = "";
        localWidget.callback?.(localWidget.value);
        idWidget.callback?.(idWidget.value);
        node.setDirtyCanvas(true, true);
        app.graph.change();
      }
      renderPickedStrip();
      pickLocal.textContent = old;
      pickLocal.disabled = false;
    });

    const toolbar = document.createElement("div");
    toolbar.style.cssText = "width:100%;display:flex;gap:6px;flex-direction:column;";
    toolbar.append(browseGallery, pickLocal);
    if (isRandom) {
      const dice = document.createElement("button");
      dice.type = "button";
      dice.textContent = "🎲 随机抽一张（不运行工作流）";
      dice.style.cssText = "width:100%;height:34px;border:1px solid #b9c9bf;border-radius:6px;background:#fff;color:#244133;cursor:pointer;font:12px sans-serif;";
      dice.onclick = async () => {
        if (String(localWidget.value || "").trim()) { dice.textContent = "已选本地图片，请先清空"; setTimeout(() => dice.textContent = "🎲 随机抽一张（不运行工作流）", 1500); return; }
        const lock = node.widgets.find((w) => w.name === "locked");
        if (lock?.value) { dice.textContent = "已锁定，请先解锁"; setTimeout(() => dice.textContent = "🎲 随机抽一张（不运行工作流）", 1500); return; }
        const cat = node.widgets.find((w) => w.name === "category");
        const params = new URLSearchParams({ category: String(cat?.value || "all"), exclude_id: String(idWidget.value || "") });
        try {
          const res = await fetch(api.apiURL("/ref_gallery/random?" + params));
          const data = await res.json();
          if (!res.ok) throw new Error(data.error || "抽取失败");
          idWidget.value = data.id;
          idWidget.callback?.(idWidget.value);
          node.setDirtyCanvas(true, true);
          app.graph.change();
        } catch (err) { dice.textContent = "抽取失败：" + err.message; setTimeout(() => dice.textContent = "🎲 随机抽一张（不运行工作流）", 2000); }
      };
      toolbar.append(dice);
    }

    node.addDOMWidget("refgallery_control", "refgallery_control", toolbar,
      { serialize: false, hideOnZoom: false, getMinHeight: () => isRandom ? 116 : 78, getMaxHeight: () => isRandom ? 116 : 78 });
    node.addDOMWidget("refgallery_preview", "refgallery_preview", previewBox,
      { serialize: false, hideOnZoom: false, getMinHeight: () => 280, getMaxHeight: () => 460 });

    const configured = node.onConfigure;
    node.onConfigure = function (config) { configured?.apply(this, arguments); updatePreview(); };
    const removed = node.onRemoved;
    node.onRemoved = function () { close(); fileInput.remove(); removed?.apply(this, arguments); };

    node.setSize([380, isRandom ? 540 : 500]);
    updatePreview();
  };
}

app.registerExtension({
  name: "comfyui-ref-gallery.browser",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === "RefGallery" || nodeData.name === "RandomRefGallery") {
      wireGalleryNode(nodeType, nodeData);
    }
  },
});
