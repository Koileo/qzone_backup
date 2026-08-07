# Qzone Archive

把 QQ 空间说说、说说图片、相册和相册原图备份到本地，同时生成机器可读的 JSON 与可离线浏览的 HTML 档案页。

## 功能

- 扫码登录并复用本地 session。
- 抓取登录账号或其他指定 QQ 号，可一次备份多个账号。
- 说说分页、去重，保存文字、时间、转发内容和图片。
- 相册列表及相册照片分页备份，优先使用原图 URL。
- 正确区分登录 QQ 与目标 QQ，支持备份其他可访问账号的相册。
- 相册列表使用服务端游标完整分页；照片和视频按拍摄时间自动归档到 `年/月` 目录。
- 支持相册视频/实况图的视频链路，并在离线 HTML 中直接播放。
- 保留拍摄时间并回写本地文件修改时间，重复执行会复用已下载文件并重试失败项。
- 图片并发下载、断点式复用已有文件，失败项保留远程 URL 和错误信息。
- 同时导出 UTF-8 JSON 和完全离线的响应式 HTML，支持搜索、分类筛选和大图查看。
- 抓取与存储核心可注入 fake API，便于离线测试。

项目只能读取当前登录账号在 QQ 空间网页中可见的内容；目标空间的访问权限会直接反映在备份结果中。

## 安装

需要 Python 3.9 或更高版本：

```bash
git clone <你的仓库地址>
cd qzone-archive
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

也可以继续使用依赖文件：

```bash
python3 -m pip install -r requirements.txt
```

首次运行会在当前目录生成 `QR.png`。使用手机 QQ 扫码后，登录信息写入 `qzone_session.json`；这两个文件均已加入 `.gitignore`。

## 使用

### 交互式菜单（推荐）

直接运行，不需要提前输入任何参数：

```bash
qzone-archive

# 或
python3 main.py
```

程序打开后会显示：

```text
1. 备份自己的说说
2. 备份别人的说说
3. 备份自己的相册
4. 备份别人的相册
5. 备份自己的说说和相册
6. 备份别人的说说和相册
7. 扫码登录 / 验证登录
8. 查看本地登录状态
9. 从 JSON 重新生成 HTML
0. 退出
```

选择相册备份后，只需确认保存目录（备份别人时还需输入目标 QQ），随后程序会列出相册名称、媒体数和访问状态，用户可输入一个或多个编号，也可直接回车选择全部。相册交互模式只下载原图/视频并生成离线 HTML，不生成 JSON；每个相册内按拍摄时间归档到 `年/月`，没有时间信息的文件进入“未分类”。完成一项操作后会自动回到主菜单。命令行参数模式仍可按需导出 JSON。

也可以显式打开菜单：

```bash
qzone-archive menu
```

#### 双击打开

- macOS：双击 `start_qzone.command`。
- Windows：双击 `start_qzone.bat`。

启动器会优先使用项目中的 `.venv` 虚拟环境。

### 参数模式（自动化脚本使用）

原有参数方式继续保留：

```bash
# 查看所有参数命令
qzone-archive --help

# 1. 备份自己的说说
qzone-archive self moods

# 2. 备份他人的说说
qzone-archive user moods 123456789

# 3. 备份自己的相册
qzone-archive self albums

# 4. 备份他人的相册，可一次指定多个 QQ
qzone-archive user albums 123456789 987654321

# 完整备份自己的说说与相册
qzone-archive self all

# 完整备份多个其他空间，QQ 也可以逗号分隔
qzone-archive user all 123456789,987654321
```

未安装命令行入口时，把 `qzone-archive` 换成 `python3 main.py` 即可。

默认目录：

```text
backups/
└── 123456789/
    ├── moods/
    │   ├── archive.json
    │   ├── index.html
    │   └── media/feeds/
    ├── albums/
    │   ├── index.html
    │   └── media/albums/相册名--相册ID/年/月/
    └── all/
        ├── archive.json
        ├── index.html
        └── media/
```

不同功能写入独立目录，不会因为单独备份说说而覆盖相册结果。直接双击对应模式下的 `index.html` 即可离线浏览。

### 辅助命令

```bash
# 扫码登录或验证当前 session
qzone-archive login

# 只查看本地 session，不访问网络
qzone-archive status

# 从已有 JSON 重新生成 HTML，不登录、不重新抓取
qzone-archive render backups/123456789/moods/archive.json

# 兼容 0.1 版的一键入口
qzone-archive backup --target 123456789
```

### 备份参数

- `user` 命令的位置参数可接收多个 QQ，也支持逗号分隔。
- `--output-dir DIR`：多账号备份根目录，默认 `backups`。
- `--format all|json|html`：默认同时生成两种格式。
- `--page-size N` / `--max-pages N`：说说分页大小和页数限制。
- 说说抓取以接口返回的总量或空页作为结束条件；中途短页会继续翻页，不再约 90 条时提前结束。
- 分页遇到 `429/500/501/502/503/504` 或临时网络异常时会在原位置自动退避重试。
- 每个成功的说说分页都会追加到 JSONL 检查点；任务中断后再次运行会从最后成功位置续传，完成导出后自动清理检查点。
- `--max-albums N` / `--max-photo-pages N`：相册及单相册照片页数限制。
- `--album NAME`：参数模式只备份指定名称相册，可重复使用。
- `--delay SECONDS`：分页请求间隔，默认 `0.5` 秒。
- `--no-media`：保留图片 URL，但不下载文件。
- `--media-concurrency N`：图片并发下载数，默认 `6`。
- `--session PATH`：指定登录缓存位置。

## JSON 格式

```json
{
  "target_qq": "123456789",
  "fetched_at": "2026-08-06T00:00:00+00:00",
  "total": 1,
  "data": [
    {
      "cur_key": "...",
      "content": "一条说说",
      "timestamp": 0,
      "images": [{"url": "https://...", "local_path": "media/feeds/...jpg"}]
    }
  ],
  "album_total": 1,
  "albums": [
    {
      "id": "...",
      "name": "旅行",
      "photo_count": 20,
      "photos": [{"url": "https://...", "local_path": "media/albums/...jpg"}]
    }
  ]
}
```

## 开发

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile main.py qzone_scraper.py qzone_api/api/*.py
```

提交改动前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。漏洞和凭据泄露问题请按 [SECURITY.md](SECURITY.md) 处理。

相册接口兼容性实现参考记录见 [REFERENCES.md](REFERENCES.md)。

## License

[MIT](LICENSE)
