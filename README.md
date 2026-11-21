# comfyui-ref-gallery · 个人参考图库节点

ComfyUI 自定义节点：**两种取图方式——从持久化图库选图，或直接加载本机任意位置的图片 → 输出 IMAGE 张量给工作流**。

这个插件**不包含任何图片**。它是从零重写的干净实现，用来替代 `comfyui-pose-gallery` 的"上传姿态"功能，而不带入后者内置素材的版权限制。代码 MIT；你导入的图片权利仍归各自权利人。

## 功能

- **浏览参考图库**：点节点上的「浏览参考图库」按钮，可上传、从文件夹批量导入、搜索、筛选、选图。图片会复制到图库存盘，永久可用。
- **加载本地图片**：点节点上的「加载本地图片」按钮，输入任意文件夹路径即可列出其中图片并选图。**图片留在原位置，不复制入库、不占额外空间**；原图被移动或删除后节点会失效。
- 两个按钮互斥：选图库图会清空本地路径，选本地图会清空图库 ID，避免混淆。
- **上传图片**：单张上传 PNG / JPEG / WebP，≤20 MiB、≤3200 万像素。服务端校验真实内容，拒绝动图、损坏图片和越界文件名。
- **文件夹批量导入**：指向本机一个文件夹，一次导入其中所有静态图片（可指定统一分类）。索引按批次一次写入，几千张也能快速导入。
- **随机节点**：点骰子即时随机预览（不运行工作流），可锁定；解锁后每次运行重新抽取，可按分类筛选。
- **删除管理**：在图库里删除图片及其全部衍生文件。
- **输出**：`image`（RGB）、`width`、`height`、`image_id`、`name`、`description`。

## 安装

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Strongcoffee2024/comfyui-ref-gallery.git comfyui-ref-gallery
```

重启 ComfyUI，刷新浏览器。唯一依赖是 ComfyUI 自带的 Pillow / NumPy / PyTorch / aiohttp，无需 `pip install`。

## 使用

1. 画布右键 → **image / Ref Gallery** → 添加「参考图库 Ref Gallery」或「随机参考图 Random Ref」。
2. 两种取图方式，按需选一个：
   - **从图库选**：点「浏览参考图库」→ 上传图片或导入文件夹 → 选中图片 → 「使用选中图片」。图片会复制进图库。
   - **加载本机图片**：点「加载本地图片」→ 填入文件夹绝对路径（可勾选含子目录）→ 「列出图片」→ 选中 → 「使用选中图片」。**不复制、不入库**，适合已经有整理好的素材目录。
3. 也可以直接把绝对路径填进节点的 `local_path` 输入框。
4. 把 `image` 输出接到 Load Image 能接的任何地方（预览、VAE Encode、ControlNet、IPAdapter 等）。

随机节点：点「🎲 随机抽一张」即时预览；选中图会自动锁定，运行工作流时固定输出该图；取消锁定则每次运行重新随机。`category` 填 `all` 表示不筛选。若 `local_path` 有值，则直接使用该本地图片，跳过随机。

图库里也可直接上传/导入/删除，**这些操作都不会把任务加入生成队列**。

## 数据与备份

所有数据存放在 ComfyUI 用户目录，与插件代码分离，升级插件不会覆盖：

```
ComfyUI/user/ref_gallery/
├── data/index.json      # 图片索引（名称、分类、标签、尺寸、哈希）
├── full/<id>.png        # 原图
├── preview/<id>.webp    # 预览
├── thumbs/<id>.webp     # 缩略图
└── local_thumbs/        # 「加载本地图片」的缩略图缓存（可安全删除，会自动重建）
```

「加载本地图片」不写入上述库，只在 `local_thumbs/` 留一份缩略图缓存。备份时备份前三项即可。可用环境变量 `COMFYUI_REF_GALLERY_DIR` 指定其他可写目录（例如容器内共享目录）。同一台 ComfyUI 服务的所有浏览器客户端共享该库，没有账号或多用户隔离。

## 接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/ref_gallery/catalog` | 图片索引与统计 |
| GET | `/ref_gallery/meta` | 数量与库路径 |
| GET | `/ref_gallery/assets/{kind}/{file}` | 读取 full/preview/thumb |
| GET | `/ref_gallery/gallery` | 图库页面 |
| GET | `/ref_gallery/random?category=&exclude_id=` | 随机挑选一张（元数据） |
| GET | `/ref_gallery/local_browser` | 本地图片浏览页 |
| GET | `/ref_gallery/local_list?folder=&recursive=` | 列出本机文件夹中的图片 |
| GET | `/ref_gallery/local_thumb?path=` | 本地图片缩略图（缓存） |
| POST | `/ref_gallery/upload` | multipart 上传，字段 `image`/`name`/`other_name`/`category`/`angle`/`tags` |
| POST | `/ref_gallery/delete` | JSON `{id}` |
| POST | `/ref_gallery/import_folder` | JSON `{folder, category}` |

## 许可

MIT。插件不内置、不下载、不镜像任何第三方图库；图片权利归各自作者。功能交互参考了 `comfyui-pose-gallery` 的上传流程，但代码为独立实现，未复制其源码或任何内置素材。此插件与原作者或任何姿势图库站点无关联。

## 对外分发检查清单

可以上传到 GitHub 并以 MIT 分发。发布前建议确认以下几点：

1. **保留 `LICENSE`**。本仓库已按发布者署名；fork 或转载时请保留原许可文本。
2. **不要顺手塞进图片**。本插件的价值之一是零素材；如果把 shisei 或其他图库的图片一起打包，就必须额外遵守那些素材各自的许可（例如 shisei 的 `LICENSE-images` / `NOTICE`，以及其姿势目录仅注明出处、不在授权范围内的约定）。最稳妥的做法是只发布代码，让用户自己导入图片。
3. **安全边界**：`/ref_gallery/import_folder` 与 `/ref_gallery/local_list` / `local_thumb` 允许 ComfyUI 服务进程读取其可访问的任意本地文件夹中的图片，`/upload`、`/delete` 也没有账号鉴权——这与 ComfyUI 本身的本地信任模型一致。只在本机或可信内网使用；若要暴露到公网，请在反向代理层加认证，不要把图库接口直接公开。
4. **依赖**：运行需要 ComfyUI 自带的 Pillow / NumPy / PyTorch / aiohttp，不需要额外 `pip install`，也没有 CDN 或外部前端资源，离线可用。
5. 发布时建议打一个 Git tag（如 `v1.0.0`），方便使用者锁定版本。

## 验证

```bash
python -m py_compile __init__.py store.py local_images.py
```
