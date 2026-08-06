"""可测试的 QQ 空间说说抓取与本地持久化工具。

网络登录和 API 实例由调用方传入，因此分页与存储逻辑可以在离线环境中用
fake API 验证，不需要真的访问 QQ 空间。
"""

from __future__ import annotations

import json
import os
import tempfile
import hashlib
import html as html_lib
import mimetypes
import re
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple, Union
from urllib.parse import urlsplit


class MessageApi(Protocol):
    async def get_messages_list(
        self, target_qq: int, g_tk: int, cookies: str, pos: int = 0, num: int = 20
    ) -> Optional[Dict[str, Any]]:
        """返回 qzone_api.ApiZone.get_messages_list 兼容的数据。"""


class AlbumApi(Protocol):
    async def get_album_list(
        self,
        target_qq: int,
        g_tk: int,
        cookies: str,
        page: int = 0,
        count: int = 30,
        login_qq: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """返回相册列表。"""

    async def get_album_photos(
        self,
        target_qq: int,
        album_id: str,
        g_tk: int,
        cookies: str,
        start: int = 0,
        count: int = 500,
        login_qq: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """返回相册内照片。"""


def normalise_qq(value: Any) -> int:
    """将 QQ API 常见的 ``o123``/``u123``/数字字符串转成整数。"""

    text = str(value).strip()
    if text[:1].lower() in {"o", "u"}:
        text = text[1:]
    if not text.isdigit():
        raise ValueError("QQ 号必须是纯数字，或以 o/u 开头的数字字符串")
    return int(text)


def cookie_header(cookies: Dict[str, Any]) -> str:
    """把 cookie 字典编码为 HTTP Cookie 请求头。"""

    return "; ".join(f"{key}={value}" for key, value in cookies.items())


def _feed_key(feed: Dict[str, Any]) -> str:
    """取得稳定的说说键，兼容不同版本解析器的字段名。"""

    for key in ("cur_key", "tid", "key", "id"):
        value = feed.get(key)
        if value not in (None, ""):
            return str(value)
    # 极少数异常响应没有 ID，保留内容而不是静默丢失。
    return json.dumps(feed, ensure_ascii=False, sort_keys=True)


async def scrape_messages(
    api: MessageApi,
    target_qq: int,
    g_tk: int,
    cookies: str,
    *,
    start_pos: int = 0,
    page_size: int = 20,
    max_pages: Optional[int] = None,
    delay: float = 0.5,
    on_page: Optional[Callable[[int, int, int], None]] = None,
) -> List[Dict[str, Any]]:
    """分页抓取说说并去重。

    ``on_page(page, position, count)`` 在每页成功解析后调用，适合 CLI 打印进度。
    空页、短页或连续重复页会结束抓取，避免接口异常时无限请求。
    """

    if page_size <= 0:
        raise ValueError("page_size 必须大于 0")
    if start_pos < 0:
        raise ValueError("start_pos 不能小于 0")
    if max_pages is not None and max_pages <= 0:
        raise ValueError("max_pages 必须大于 0")

    # 延迟导入，单元测试和离线使用不需要安装异步库。
    if delay < 0:
        raise ValueError("delay 不能小于 0")
    if delay:
        import asyncio

    position = start_pos
    page = 0
    feeds: List[Dict[str, Any]] = []
    seen = set()

    while max_pages is None or page < max_pages:
        result = await api.get_messages_list(
            target_qq=target_qq,
            g_tk=g_tk,
            cookies=cookies,
            pos=position,
            num=page_size,
        )
        if not isinstance(result, dict):
            raise RuntimeError(f"第 {page + 1} 页返回格式无效: {type(result).__name__}")
        if result.get("status") == "error":
            raise RuntimeError(str(result.get("message", "QQ 空间接口返回错误")))

        batch = result.get("data") or []
        if not isinstance(batch, list):
            raise RuntimeError("接口返回的 data 不是列表")
        page += 1

        new_count = 0
        for item in batch:
            if not isinstance(item, dict):
                continue
            key = _feed_key(item)
            if key in seen:
                continue
            seen.add(key)
            feeds.append(item)
            new_count += 1

        if on_page:
            on_page(page, position, new_count)

        if not batch or len(batch) < page_size or new_count == 0:
            break
        position += page_size
        if delay:
            await asyncio.sleep(delay)

    return feeds


async def scrape_albums(
    api: AlbumApi,
    target_qq: int,
    g_tk: int,
    cookies: str,
    *,
    login_qq: Optional[int] = None,
    max_albums: Optional[int] = None,
    album_page_size: int = 30,
    photo_page_size: int = 500,
    max_photo_pages: Optional[int] = None,
    album_names: Optional[List[str]] = None,
    album_selector: Optional[Callable[[List[Dict[str, Any]]], Optional[List[str]]]] = None,
    delay: float = 0.5,
    on_album: Optional[Callable[[int, int, str, int], None]] = None,
) -> List[Dict[str, Any]]:
    """抓取相册与相册内照片元数据，保留无权访问相册的基本信息。"""

    if max_albums is not None and max_albums <= 0:
        raise ValueError("max_albums 必须大于 0")
    if album_page_size <= 0:
        raise ValueError("album_page_size 必须大于 0")
    if photo_page_size <= 0:
        raise ValueError("photo_page_size 必须大于 0")
    if max_photo_pages is not None and max_photo_pages <= 0:
        raise ValueError("max_photo_pages 必须大于 0")
    if delay < 0:
        raise ValueError("delay 不能小于 0")

    import asyncio

    operator = login_qq or target_qq
    albums: List[Dict[str, Any]] = []
    seen_albums = set()
    offset = 0
    while True:
        result = await api.get_album_list(
            target_qq,
            g_tk,
            cookies,
            page=offset,
            count=album_page_size,
            login_qq=operator,
        )
        if not isinstance(result, dict):
            raise RuntimeError("相册列表返回格式无效")
        if result.get("status") == "error":
            raise RuntimeError(str(result.get("message", "相册列表接口返回错误")))
        batch = result.get("data") or []
        if not isinstance(batch, list):
            raise RuntimeError("相册列表 data 不是列表")
        before_count = len(albums)
        for item in batch:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or item.get("name") or item)
            if key in seen_albums:
                continue
            seen_albums.add(key)
            albums.append(dict(item))
        new_count = len(albums) - before_count
        total_raw = result.get("total_available")
        total_available = int(total_raw) if total_raw not in (None, "") else 0
        next_start = result.get("next_start")
        if not batch or new_count == 0 or (total_available and len(albums) >= total_available):
            break
        if next_start is None:
            if len(batch) < album_page_size:
                break
            next_start = offset + album_page_size
        next_start = int(next_start)
        if next_start <= offset:
            break
        offset = next_start
        if delay:
            await asyncio.sleep(delay)

    if album_selector:
        selection = album_selector(albums)
        if selection is not None:
            selected_ids = {str(value) for value in selection}
            albums = [album for album in albums if str(album.get("id", "")) in selected_ids]
    else:
        selected_names = {name.strip() for name in (album_names or []) if name.strip()}
        if selected_names:
            albums = [album for album in albums if str(album.get("name", "")) in selected_names]
    if max_albums is not None:
        albums = albums[:max_albums]

    for album_index, album in enumerate(albums, 1):
        album_id = str(album.get("id", ""))
        photos: List[Dict[str, Any]] = []
        seen = set()
        start = 0
        page = 0
        expected = int(album.get("photo_count", 0) or 0)
        if album_id and int(album.get("allow_access", 1) or 0):
            while max_photo_pages is None or page < max_photo_pages:
                page_result = await api.get_album_photos(
                    target_qq,
                    album_id,
                    g_tk,
                    cookies,
                    start=start,
                    count=photo_page_size,
                    login_qq=operator,
                )
                if not isinstance(page_result, dict):
                    album["backup_error"] = "照片列表返回格式无效"
                    break
                if page_result.get("status") == "error":
                    album["backup_error"] = str(page_result.get("message", "照片列表接口返回错误"))
                    break
                batch = page_result.get("data") or []
                if not isinstance(batch, list):
                    album["backup_error"] = "照片列表 data 不是列表"
                    break
                page += 1
                for photo in batch:
                    if not isinstance(photo, dict):
                        continue
                    key = str(photo.get("id") or photo.get("url") or photo)
                    if key in seen:
                        continue
                    seen.add(key)
                    photos.append(photo)
                expected = max(expected, int(page_result.get("total", 0) or 0))
                if not batch or len(batch) < photo_page_size or (expected and len(photos) >= expected):
                    break
                start += photo_page_size
                if delay:
                    await asyncio.sleep(delay)
            resolver = getattr(api, "get_video_download_url", None)
            if resolver:
                for photo in photos:
                    if not photo.get("is_video") or not photo.get("sloc"):
                        continue
                    video_result = await resolver(
                        target_qq,
                        album_id,
                        str(photo["sloc"]),
                        g_tk,
                        cookies,
                        login_qq=operator,
                    )
                    if isinstance(video_result, dict) and video_result.get("status") == "ok":
                        photo["video_url"] = video_result.get("url", "")
                    else:
                        photo["video_error"] = (
                            video_result.get("message", "视频地址获取失败")
                            if isinstance(video_result, dict)
                            else "视频地址获取失败"
                        )
        album["photos"] = photos
        album["photo_count"] = max(expected, len(photos))
        if on_album:
            on_album(album_index, len(albums), str(album.get("name", "未命名相册")), len(photos))
        if delay and album_index < len(albums):
            await asyncio.sleep(delay)
    return albums


def build_snapshot(
    target_qq: int,
    feeds: List[Dict[str, Any]],
    albums: Optional[List[Dict[str, Any]]] = None,
    *,
    included: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """构造稳定、便于二次处理的 JSON 文档。"""

    return {
        "target_qq": str(target_qq),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total": len(feeds),
        "data": feeds,
        "album_total": len(albums or []),
        "albums": albums or [],
        "included": included or ["moods", "albums"],
    }


def save_snapshot(snapshot: Dict[str, Any], output: Union[os.PathLike, str]) -> Path:
    """以 UTF-8 JSON 原子写入 ``output``，避免中断留下半个文件。"""

    destination = Path(output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def _slug(value: Any, fallback: str = "item") -> str:
    text = re.sub(r"[^\w.-]+", "-", str(value or ""), flags=re.UNICODE).strip("-._")
    return text[:80] or fallback


def _best_url(item: Dict[str, Any]) -> str:
    for key in ("video_url", "download_url", "raw", "origin_url", "url", "preview_url", "pre", "small"):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return ""


def _media_references(snapshot: Dict[str, Any]) -> Iterable[Tuple[Dict[str, Any], str, str]]:
    """遍历所有可下载图片，返回 (字段对象, 分类目录, 文件名前缀)。"""

    for feed_index, feed in enumerate(snapshot.get("data", []), 1):
        if not isinstance(feed, dict):
            continue
        feed_id = _slug(feed.get("cur_key") or feed.get("tid") or feed_index, f"feed-{feed_index}")
        for image_index, image in enumerate(feed.get("images", []), 1):
            if isinstance(image, dict):
                yield image, f"feeds/{feed_id}", f"image-{image_index:03d}"
        repost = feed.get("repost")
        if isinstance(repost, dict):
            for image_index, image in enumerate(repost.get("images", []), 1):
                if isinstance(image, dict):
                    yield image, f"feeds/{feed_id}", f"repost-{image_index:03d}"

    for album_index, album in enumerate(snapshot.get("albums", []), 1):
        if not isinstance(album, dict):
            continue
        album_id = _slug(album.get("id") or album_index, f"album-{album_index}")
        album_name = _slug(album.get("name"), "unnamed-album")
        album_dir = f"{album_name}--{album_id}"
        cover_url = album.get("cover_url")
        if isinstance(cover_url, str) and cover_url.startswith(("http://", "https://")):
            cover = {"url": cover_url}
            album["_cover_media"] = cover
            yield cover, f"albums/{album_dir}", "cover"
        for photo_index, photo in enumerate(album.get("photos", []), 1):
            if isinstance(photo, dict):
                prefix = _slug(photo.get("id") or photo_index, f"photo-{photo_index}")
                timestamp = _media_timestamp(photo)
                time_dir = (
                    datetime.fromtimestamp(timestamp).strftime("%Y/%m")
                    if timestamp
                    else "未分类"
                )
                yield photo, f"albums/{album_dir}/{time_dir}", prefix


def _fetch_binary(url: str, cookies: str, timeout: float) -> Tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (QzoneArchive/1.0)",
            "Referer": "https://user.qzone.qq.com/",
            "Cookie": cookies,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type()


def _extension(url: str, content_type: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif", ".mp4", ".mov", ".webm"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    guessed = mimetypes.guess_extension(content_type or "") or ".jpg"
    return ".jpg" if guessed in {".jpe", ".jpeg"} else guessed


def _media_timestamp(item: Dict[str, Any]) -> int:
    for key in ("captured_time", "uploaded_time", "timestamp"):
        try:
            value = int(item.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return 0


def _apply_media_time(path: Path, item: Dict[str, Any]) -> None:
    timestamp = _media_timestamp(item)
    if not timestamp:
        return
    try:
        os.utime(path, (timestamp, timestamp))
    except OSError as exc:
        item["time_restore_error"] = str(exc)


async def download_snapshot_media(
    snapshot: Dict[str, Any],
    media_dir: Union[os.PathLike, str],
    *,
    cookies: str = "",
    concurrency: int = 6,
    timeout: float = 30,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """并发下载说说及相册照片，返回带 local_path 的快照副本与统计。"""

    if concurrency <= 0:
        raise ValueError("concurrency 必须大于 0")
    if timeout <= 0:
        raise ValueError("timeout 必须大于 0")
    root = Path(media_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    archive_root = root.parent
    copied = deepcopy(snapshot)
    references = list(_media_references(copied))
    report = {"downloaded": 0, "skipped": 0, "failed": 0}

    import asyncio

    semaphore = asyncio.Semaphore(concurrency)

    async def download_one(item: Dict[str, Any], category: str, prefix: str) -> None:
        item.pop("download_error", None)
        url = _best_url(item)
        if not url:
            report["failed"] += 1
            item["download_error"] = "没有可用图片地址"
            return
        stable_identity = str(item.get("sloc") or item.get("id") or url)
        digest = hashlib.sha256(stable_identity.encode("utf-8")).hexdigest()[:12]
        destination_dir = root / category
        destination_dir.mkdir(parents=True, exist_ok=True)
        base = f"{_slug(prefix)}-{digest}"
        existing = next(destination_dir.glob(f"{base}.*"), None)
        if existing and existing.is_file():
            item["local_path"] = existing.relative_to(archive_root).as_posix()
            _apply_media_time(existing, item)
            report["skipped"] += 1
            return
        try:
            async with semaphore:
                data, content_type = await asyncio.to_thread(_fetch_binary, url, cookies, timeout)
            destination = destination_dir / f"{base}{_extension(url, content_type)}"
            fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=str(destination_dir))
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            item["local_path"] = destination.relative_to(archive_root).as_posix()
            _apply_media_time(destination, item)
            report["downloaded"] += 1
        except Exception as exc:
            item["download_error"] = str(exc)
            report["failed"] += 1

    await asyncio.gather(*(download_one(*reference) for reference in references))
    for album in copied.get("albums", []):
        if isinstance(album, dict):
            cover = album.pop("_cover_media", None)
            if isinstance(cover, dict) and cover.get("local_path"):
                album["cover_local_path"] = cover["local_path"]
            if isinstance(cover, dict) and cover.get("download_error"):
                album["cover_download_error"] = cover["download_error"]
    return copied, report


def _display_time(value: Any) -> Tuple[str, str]:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if not timestamp:
        return "时间未记录", ""
    moment = datetime.fromtimestamp(timestamp).astimezone()
    return moment.strftime("%Y年%m月%d日 %H:%M"), moment.isoformat()


def _image_source(image: Dict[str, Any]) -> str:
    local = image.get("local_path")
    return str(local) if local else _best_url(image)


def _render_image(image: Dict[str, Any], alt: str) -> str:
    source = _image_source(image)
    if not source:
        return ""
    src = html_lib.escape(source, quote=True)
    label = html_lib.escape(str(image.get("description") or image.get("desc") or alt), quote=True)
    is_video = bool(image.get("is_video")) or Path(urlsplit(source).path).suffix.lower() in {
        ".mp4",
        ".mov",
        ".webm",
    }
    if is_video:
        poster = html_lib.escape(str(image.get("preview_url") or ""), quote=True)
        poster_attr = f' poster="{poster}"' if poster else ""
        return (
            f'<div class="photo video"><video src="{src}"{poster_attr} controls '
            f'preload="metadata" aria-label="{label}"></video></div>'
        )
    return (
        '<button class="photo" type="button" data-full="{src}" aria-label="查看大图：{label}">'
        '<img src="{src}" alt="{label}" loading="lazy" decoding="async">'
        "</button>"
    ).format(src=src, label=label)


def _render_feed(feed: Dict[str, Any], index: int) -> str:
    display_time, iso_time = _display_time(feed.get("timestamp"))
    content = html_lib.escape(str(feed.get("content") or "（无文字）"))
    images = "".join(
        _render_image(image, f"说说照片 {image_index}")
        for image_index, image in enumerate(feed.get("images", []), 1)
        if isinstance(image, dict)
    )
    image_count = sum(1 for image in feed.get("images", []) if isinstance(image, dict))
    repost_html = ""
    repost = feed.get("repost")
    if isinstance(repost, dict):
        repost_content = html_lib.escape(str(repost.get("content") or "转发内容"))
        repost_author = html_lib.escape(str(repost.get("author") or repost.get("uin") or "原作者"))
        repost_images = "".join(
            _render_image(image, f"转发照片 {image_index}")
            for image_index, image in enumerate(repost.get("images", []), 1)
            if isinstance(image, dict)
        )
        repost_html = (
            f'<aside class="repost"><span class="utility">转自 {repost_author}</span>'
            f'<p>{repost_content}</p><div class="photo-strip">{repost_images}</div></aside>'
        )
    search = html_lib.escape(f"{content} {display_time}", quote=True)
    return f"""
    <article class="memory-card searchable" data-kind="mood" data-search="{search}">
      <div class="rail-mark"><span>{index:03d}</span></div>
      <div class="memory-body">
        <header class="memory-meta">
          <time datetime="{html_lib.escape(iso_time, quote=True)}">{display_time}</time>
          <span>{image_count} 张照片</span>
        </header>
        <p class="memory-copy">{content}</p>
        <div class="photo-strip">{images}</div>
        {repost_html}
      </div>
    </article>"""


def _render_album(album: Dict[str, Any], index: int) -> str:
    name = html_lib.escape(str(album.get("name") or "未命名相册"))
    description = html_lib.escape(str(album.get("description") or "没有相册说明"))
    display_time, iso_time = _display_time(album.get("updated_time") or album.get("created_time"))
    photos = [photo for photo in album.get("photos", []) if isinstance(photo, dict)]
    photo_html = "".join(
        _render_image(photo, str(photo.get("name") or f"{name}照片 {photo_index}"))
        for photo_index, photo in enumerate(photos, 1)
    )
    expected = int(album.get("photo_count", len(photos)) or len(photos))
    access_note = ""
    if not int(album.get("allow_access", 1) or 0):
        access_note = '<p class="empty-note">当前登录账号没有浏览该相册照片的权限。</p>'
    elif album.get("backup_error"):
        access_note = '<p class="empty-note">照片元数据获取未完成，请稍后重新备份。</p>'
    elif not photos:
        access_note = '<p class="empty-note">这个相册暂无可展示的照片。</p>'
    search = html_lib.escape(f"{name} {description} {display_time}", quote=True)
    cover_source = str(album.get("cover_local_path") or album.get("cover_url") or "")
    safe_cover = cover_source.replace("\\", "").replace("'", "%27").replace('"', "%22").replace(")", "%29")
    cover_style = (
        f' style="--album-cover:url(\'{html_lib.escape(safe_cover, quote=True)}\')"'
        if cover_source
        else ""
    )
    return f"""
    <details class="album-card searchable" data-kind="album" data-search="{search}" open>
      <summary{cover_style}>
        <span class="album-index">ALB—{index:02d}</span>
        <span class="album-title">{name}</span>
        <span class="album-count">已备份 {len(photos)} / 记录 {expected}</span>
      </summary>
      <div class="album-body">
        <div class="album-notes">
          <p>{description}</p>
          <time datetime="{html_lib.escape(iso_time, quote=True)}">最后更新 {display_time}</time>
        </div>
        {access_note}
        <div class="album-grid">{photo_html}</div>
      </div>
    </details>"""


def render_archive_html(snapshot: Dict[str, Any]) -> str:
    """生成单文件、无外部依赖的离线照片档案 HTML。"""

    target = html_lib.escape(str(snapshot.get("target_qq") or "未知账号"))
    fetched = html_lib.escape(str(snapshot.get("fetched_at") or ""))
    feeds = [item for item in snapshot.get("data", []) if isinstance(item, dict)]
    albums = [item for item in snapshot.get("albums", []) if isinstance(item, dict)]
    raw_included = snapshot.get("included")
    included = set(raw_included) if isinstance(raw_included, list) else {"moods", "albums"}
    photo_total = sum(
        len([image for image in feed.get("images", []) if isinstance(image, dict)]) for feed in feeds
    ) + sum(len([photo for photo in album.get("photos", []) if isinstance(photo, dict)]) for album in albums)
    feed_html = "".join(_render_feed(feed, index) for index, feed in enumerate(feeds, 1))
    album_html = "".join(_render_album(album, index) for index, album in enumerate(albums, 1))
    if not feed_html:
        feed_html = '<p class="section-empty">没有抓取到可展示的说说。</p>'
    if not album_html:
        album_html = '<p class="section-empty">没有抓取到可展示的相册。</p>'
    mood_section = ""
    if "moods" in included:
        mood_section = f"""
    <section class="moods" data-section="mood">
      <header class="section-head"><h2>说说时间线</h2><span class="utility">{len(feeds)} ENTRIES</span></header>
      <div class="timeline">{feed_html}</div>
    </section>"""
    album_section = ""
    if "albums" in included:
        album_section = f"""
    <section class="albums" data-section="album">
      <header class="section-head"><h2>相册底片册</h2><span class="utility">{len(albums)} ALBUMS</span></header>
      {album_html}
    </section>"""
    filter_buttons = ['<button type="button" data-filter="all" aria-pressed="true">全部</button>']
    if "moods" in included:
        filter_buttons.append('<button type="button" data-filter="mood" aria-pressed="false">说说</button>')
    if "albums" in included:
        filter_buttons.append('<button type="button" data-filter="album" aria-pressed="false">相册</button>')
    filter_html = "".join(filter_buttons)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>空间档案 · {target}</title>
  <style>
    :root {{
      --darkroom: #0b1e26;
      --darkroom-soft: #17323a;
      --paper: #eaf2f2;
      --paper-deep: #d6e4e3;
      --ink: #172326;
      --cyan-tape: #4e9ca4;
      --timestamp: #e5a84b;
      --hairline: rgba(23, 35, 38, .19);
      --display: "Songti SC", "STSong", "Noto Serif CJK SC", serif;
      --body: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      --utility: "SFMono-Regular", "Cascadia Code", "Roboto Mono", monospace;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; background: var(--paper); }}
    body {{ margin: 0; color: var(--ink); background: var(--paper); font-family: var(--body); }}
    button, input, summary {{ font: inherit; }}
    button:focus-visible, input:focus-visible, summary:focus-visible {{ outline: 3px solid var(--timestamp); outline-offset: 3px; }}
    .hero {{ min-height: 62vh; display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr); background: var(--darkroom); color: var(--paper); border-bottom: 10px solid var(--timestamp); }}
    .hero-main {{ padding: clamp(40px, 8vw, 112px); display: flex; flex-direction: column; justify-content: space-between; gap: 72px; }}
    .eyebrow, .utility {{ font-family: var(--utility); text-transform: uppercase; letter-spacing: .14em; font-size: 12px; }}
    h1 {{ margin: 0; max-width: 10ch; font-family: var(--display); font-size: clamp(54px, 10vw, 148px); font-weight: 700; line-height: .86; letter-spacing: -.055em; }}
    h1 span {{ display: block; color: var(--timestamp); font-family: var(--utility); font-size: .18em; letter-spacing: .08em; margin-bottom: 18px; }}
    .hero-side {{ border-left: 1px solid rgba(234,242,242,.22); padding: 40px; display: grid; align-content: end; gap: 1px; }}
    .stat {{ padding: 22px 0; border-top: 1px solid rgba(234,242,242,.22); display: flex; justify-content: space-between; align-items: baseline; }}
    .stat strong {{ font-family: var(--display); font-size: 42px; }}
    .toolbar {{ position: sticky; top: 0; z-index: 20; display: grid; grid-template-columns: auto 1fr; gap: 20px; align-items: center; padding: 14px clamp(20px, 5vw, 72px); background: rgba(234,242,242,.94); border-bottom: 1px solid var(--hairline); backdrop-filter: blur(16px); }}
    .tabs {{ display: flex; gap: 6px; }}
    .tabs button {{ border: 1px solid var(--ink); background: transparent; color: var(--ink); padding: 9px 14px; cursor: pointer; }}
    .tabs button[aria-pressed="true"] {{ background: var(--ink); color: var(--paper); }}
    .search {{ width: min(460px, 100%); justify-self: end; border: 0; border-bottom: 1px solid var(--ink); background: transparent; padding: 10px 4px; color: var(--ink); }}
    main {{ width: min(1440px, 100%); margin: 0 auto; padding: clamp(40px, 8vw, 112px) clamp(20px, 6vw, 88px); }}
    .section-head {{ margin: 0 0 44px; display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; border-bottom: 1px solid var(--ink); padding-bottom: 14px; }}
    .section-head h2 {{ margin: 0; font-family: var(--display); font-size: clamp(38px, 6vw, 78px); letter-spacing: -.035em; }}
    .timeline {{ position: relative; padding-left: 66px; }}
    .timeline::before {{ content: ""; position: absolute; left: 23px; top: 0; bottom: 0; width: 1px; background: var(--cyan-tape); }}
    .memory-card {{ position: relative; display: grid; grid-template-columns: minmax(0, 1fr); padding: 0 0 clamp(52px, 8vw, 112px); }}
    .rail-mark {{ position: absolute; left: -66px; top: 0; width: 47px; display: grid; place-items: center; }}
    .rail-mark::before {{ content: ""; width: 11px; height: 11px; border-radius: 50%; background: var(--timestamp); box-shadow: 0 0 0 7px var(--paper); }}
    .rail-mark span {{ margin-top: 10px; writing-mode: vertical-rl; font-family: var(--utility); font-size: 10px; color: #4d6468; }}
    .memory-meta {{ display: flex; justify-content: space-between; gap: 20px; font-family: var(--utility); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; border-top: 1px solid var(--ink); padding-top: 12px; }}
    .memory-copy {{ max-width: 46ch; margin: 28px 0; font-family: var(--display); font-size: clamp(24px, 3.2vw, 44px); line-height: 1.45; white-space: pre-wrap; }}
    .photo-strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(210px, 100%), 1fr)); gap: 8px; }}
    .photo {{ position: relative; display: block; width: 100%; aspect-ratio: 4/3; border: 0; padding: 0; overflow: hidden; background: var(--paper-deep); cursor: zoom-in; }}
    .photo img, .photo video {{ width: 100%; height: 100%; object-fit: cover; display: block; transition: transform .35s ease, filter .35s ease; }}
    .photo.video {{ cursor: default; background: var(--darkroom); }}
    .photo:hover img {{ transform: scale(1.025); filter: contrast(1.04); }}
    .repost {{ margin-top: 24px; border-left: 5px solid var(--cyan-tape); background: var(--paper-deep); padding: 24px; }}
    .repost p {{ margin: 10px 0 20px; white-space: pre-wrap; }}
    .albums {{ margin-top: clamp(80px, 14vw, 180px); }}
    .album-card {{ border-bottom: 1px solid var(--ink); }}
    .album-card summary {{ position: relative; isolation: isolate; cursor: pointer; list-style: none; display: grid; grid-template-columns: 100px minmax(0,1fr) auto; align-items: end; gap: 24px; min-height: 150px; padding: 28px 0; overflow: hidden; }}
    .album-card summary::before {{ content: ""; position: absolute; inset: 0 45% 0 0; z-index: -2; background: var(--album-cover) center/cover no-repeat; opacity: .16; filter: grayscale(1); }}
    .album-card summary::after {{ content: ""; position: absolute; inset: 0; z-index: -1; background: linear-gradient(90deg, transparent, var(--paper) 56%); }}
    .album-card summary::-webkit-details-marker {{ display: none; }}
    .album-index, .album-count {{ font-family: var(--utility); font-size: 11px; letter-spacing: .08em; }}
    .album-title {{ font-family: var(--display); font-size: clamp(36px, 5vw, 68px); line-height: 1; }}
    .album-body {{ padding: 0 0 54px; }}
    .album-notes {{ display: flex; justify-content: space-between; gap: 24px; margin: 0 0 26px 124px; color: #42585c; }}
    .album-notes p {{ margin: 0; max-width: 52ch; }}
    .album-notes time {{ font-family: var(--utility); font-size: 11px; white-space: nowrap; }}
    .album-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 6px; }}
    .album-grid .photo:nth-child(5n+1) {{ grid-column: span 2; grid-row: span 2; }}
    .empty-note, .section-empty {{ padding: 22px; border: 1px dashed var(--hairline); color: #53686c; }}
    [hidden] {{ display: none !important; }}
    footer {{ background: var(--darkroom); color: var(--paper); padding: 34px clamp(20px, 6vw, 88px); display: flex; justify-content: space-between; gap: 24px; font-family: var(--utility); font-size: 11px; }}
    dialog {{ width: min(94vw, 1400px); height: min(92vh, 1000px); border: 0; padding: 0; background: transparent; }}
    dialog::backdrop {{ background: rgba(4, 13, 17, .92); }}
    dialog img {{ width: 100%; height: 100%; object-fit: contain; }}
    .close-lightbox {{ position: fixed; right: 24px; top: 20px; z-index: 2; width: 44px; height: 44px; border: 1px solid var(--paper); border-radius: 50%; background: var(--darkroom); color: var(--paper); cursor: pointer; }}
    @media (max-width: 760px) {{
      .hero {{ grid-template-columns: 1fr; }} .hero-side {{ border-left: 0; border-top: 1px solid rgba(234,242,242,.22); }}
      .toolbar {{ grid-template-columns: 1fr; }} .search {{ justify-self: stretch; width: 100%; }}
      .timeline {{ padding-left: 42px; }} .timeline::before {{ left: 8px; }} .rail-mark {{ left: -42px; width: 18px; }} .rail-mark span {{ display: none; }}
      .album-card summary {{ grid-template-columns: 1fr auto; }} .album-index {{ grid-column: 1/-1; }} .album-notes {{ margin-left: 0; flex-direction: column; }}
      .album-grid {{ grid-template-columns: repeat(2, 1fr); }} footer {{ flex-direction: column; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ html {{ scroll-behavior: auto; }} .photo img {{ transition: none; }} }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-main">
      <span class="eyebrow">QZONE ARCHIVE / LOCAL COPY</span>
      <h1><span>QQ {target}</span>空间档案</h1>
    </div>
    <aside class="hero-side" aria-label="备份摘要">
      <div class="stat"><span>说说</span><strong>{len(feeds)}</strong></div>
      <div class="stat"><span>相册</span><strong>{len(albums)}</strong></div>
      <div class="stat"><span>照片记录</span><strong>{photo_total}</strong></div>
    </aside>
  </header>
  <nav class="toolbar" aria-label="档案筛选">
    <div class="tabs">
      {filter_html}
    </div>
    <input class="search" type="search" placeholder="搜索日期、文字或相册名" aria-label="搜索档案">
  </nav>
  <main>
    {mood_section}
    {album_section}
  </main>
  <footer><span>QQ {target} · 本地静态备份</span><span>生成时间 {fetched}</span></footer>
  <dialog id="lightbox" aria-label="照片大图">
    <button class="close-lightbox" type="button" aria-label="关闭">×</button>
    <img alt="照片大图">
  </dialog>
  <script>
    const cards = [...document.querySelectorAll('.searchable')];
    const sections = [...document.querySelectorAll('[data-section]')];
    const search = document.querySelector('.search');
    let activeFilter = 'all';
    function applyFilter() {{
      const term = search.value.trim().toLocaleLowerCase();
      cards.forEach(card => {{
        const kindMatch = activeFilter === 'all' || card.dataset.kind === activeFilter;
        const textMatch = !term || card.dataset.search.toLocaleLowerCase().includes(term);
        card.hidden = !(kindMatch && textMatch);
      }});
      sections.forEach(section => section.hidden = activeFilter !== 'all' && section.dataset.section !== activeFilter);
    }}
    document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {{
      activeFilter = button.dataset.filter;
      document.querySelectorAll('[data-filter]').forEach(item => item.setAttribute('aria-pressed', item === button ? 'true' : 'false'));
      applyFilter();
    }}));
    search.addEventListener('input', applyFilter);
    const lightbox = document.querySelector('#lightbox');
    const lightboxImage = lightbox.querySelector('img');
    document.addEventListener('click', event => {{
      const photo = event.target.closest('[data-full]');
      if (!photo) return;
      lightboxImage.src = photo.dataset.full;
      lightboxImage.alt = photo.getAttribute('aria-label').replace('查看大图：', '');
      lightbox.showModal();
    }});
    lightbox.querySelector('button').addEventListener('click', () => lightbox.close());
    lightbox.addEventListener('click', event => {{ if (event.target === lightbox) lightbox.close(); }});
  </script>
</body>
</html>
"""


def save_archive_html(snapshot: Dict[str, Any], output: Union[os.PathLike, str]) -> Path:
    """原子保存离线 HTML。"""

    destination = Path(output).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = render_archive_html(snapshot)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


__all__ = [
    "AlbumApi",
    "MessageApi",
    "build_snapshot",
    "cookie_header",
    "download_snapshot_media",
    "normalise_qq",
    "render_archive_html",
    "save_archive_html",
    "save_snapshot",
    "scrape_albums",
    "scrape_messages",
]
