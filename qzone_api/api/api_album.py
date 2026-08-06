"""QQ 空间相册、照片与视频读取接口。"""

import json
import re
from datetime import datetime
from http.cookies import SimpleCookie
from typing import Any, Dict, List, Optional

from loguru import logger

from .api_base import ApiBase
from .api_parms import get_album_list, get_album_photos, get_video_info


def _decode_jsonp(content: Any) -> Dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise TypeError("相册接口返回值不是文本或字典")
    text = content.strip()
    match = re.match(r"^[\w$.]+\s*\((.*)\)\s*;?\s*$", text, re.DOTALL)
    payload = match.group(1) if match else text
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        import demjson3

        parsed = demjson3.decode(payload)
    if not isinstance(parsed, dict):
        raise TypeError("相册 JSONP 内容不是对象")
    return parsed


def _pick(data: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _as_timestamp(value: Any) -> int:
    if value in (None, "", 0, "0"):
        return 0
    if isinstance(value, (int, float)) or str(value).isdigit():
        return _as_int(value)
    text = str(value).strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return int(datetime.strptime(text[:19], pattern).timestamp())
        except ValueError:
            continue
    return 0


def _prefer_original(url: Any) -> str:
    text = str(url or "")
    if "b&bo=" in text:
        text = text.replace("b&bo=", "o&bo=", 1)
    return text


def parse_album_list(content: Any) -> Dict[str, Any]:
    """归一化相册列表，并保留真实分页游标。"""
    try:
        parsed = _decode_jsonp(content)
        if parsed.get("code", 0) not in (0, "0"):
            raise RuntimeError(parsed.get("message") or parsed.get("msg") or "相册列表接口返回错误")
        data = parsed.get("data") or {}
        raw: List[Dict[str, Any]] = []
        for key in ("albumList", "albumListModeSort", "albums"):
            candidate = data.get(key) if isinstance(data, dict) else None
            if isinstance(candidate, list):
                raw = candidate
                break
        if not raw and isinstance(parsed.get("albumList"), list):
            raw = parsed["albumList"]

        albums = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            album_id = str(_pick(item, "id", "albumid", "albumId"))
            if not album_id:
                continue
            albums.append(
                {
                    "id": album_id,
                    "name": str(_pick(item, "name", "albumname", default="未命名相册")),
                    "description": str(_pick(item, "desc", "description")),
                    "cover_url": _prefer_original(_pick(item, "coverurl", "coverUrl", "pre")),
                    "photo_count": _as_int(_pick(item, "total", "picnum", "photoCount", default=0)),
                    "created_time": _as_timestamp(_pick(item, "createtime", "createTime")),
                    "updated_time": _as_timestamp(
                        _pick(item, "lastuploadtime", "modifytime", "updateTime")
                    ),
                    "allow_access": _as_int(_pick(item, "allowAccess", default=1), 1),
                    "photos": [],
                }
            )

        next_start = _as_int(data.get("nextPageStart"), -1) if isinstance(data, dict) else -1
        total_available_raw = _as_int(data.get("albumsInUser"), -1) if isinstance(data, dict) else -1
        return {
            "status": "ok",
            "total": len(albums),
            "total_available": None if total_available_raw < 0 else total_available_raw,
            "next_start": None if next_start < 0 else next_start,
            "data": albums,
        }
    except Exception as exc:
        logger.error(f"解析相册列表失败: {exc}")
        return {"status": "error", "message": str(exc), "data": []}


def parse_photo_list(content: Any) -> Dict[str, Any]:
    """归一化照片/视频字段，优先保留原图和拍摄时间。"""
    try:
        parsed = _decode_jsonp(content)
        if parsed.get("code", 0) not in (0, "0"):
            raise RuntimeError(parsed.get("message") or parsed.get("msg") or "照片列表接口返回错误")
        data = parsed.get("data") or {}
        raw = data.get("photoList", []) if isinstance(data, dict) else []
        photos = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            sloc = str(_pick(item, "sloc", "lloc"))
            photo_id = str(_pick(item, "id", "photoId", "sloc", "lloc"))
            raw_url = _prefer_original(_pick(item, "raw", "origin_url", "originUrl", "url", "pre"))
            if not photo_id and not raw_url:
                continue
            shoot_time_raw = str(_pick(item, "rawshoottime", "shoottime"))
            upload_time_raw = str(_pick(item, "uploadtime"))
            is_video = _as_bool(_pick(item, "is_video", "isVideo", default=False))
            photos.append(
                {
                    "id": photo_id,
                    "sloc": sloc,
                    "name": str(_pick(item, "name", default="媒体" if is_video else "照片")),
                    "description": str(_pick(item, "desc", "description")),
                    "url": raw_url,
                    "raw": raw_url,
                    "origin_url": _prefer_original(_pick(item, "origin_url", "originUrl")),
                    "preview_url": str(_pick(item, "pre", "small3", "small2", "small", "url")),
                    "width": _as_int(_pick(item, "width", default=0)),
                    "height": _as_int(_pick(item, "height", default=0)),
                    "shoot_time": shoot_time_raw,
                    "upload_time": upload_time_raw,
                    "captured_time": _as_timestamp(shoot_time_raw) or _as_timestamp(upload_time_raw),
                    "uploaded_time": _as_timestamp(upload_time_raw),
                    "is_video": is_video,
                    "media_type": "video" if is_video else "image",
                }
            )
        total = _as_int(_pick(data, "totalInAlbum", "total", default=len(photos)), len(photos))
        return {"status": "ok", "total": total, "data": photos}
    except Exception as exc:
        logger.error(f"解析照片列表失败: {exc}")
        return {"status": "error", "message": str(exc), "data": []}


def parse_video_info(content: Any) -> Dict[str, Any]:
    """从浮层接口中提取当前媒体的视频直链。"""
    try:
        parsed = _decode_jsonp(content)
        if parsed.get("code", 0) not in (0, "0"):
            raise RuntimeError(parsed.get("message") or "视频接口返回错误")
        data = parsed.get("data") or {}
        photos = data.get("photos") or []
        if not isinstance(photos, list) or not photos:
            raise RuntimeError("视频接口没有返回媒体")
        position = min(max(_as_int(data.get("picPosInPage"), 0), 0), len(photos) - 1)
        video = photos[position] if isinstance(photos[position], dict) else {}
        info = video.get("video_info") or video.get("videoInfo") or {}
        url = str(_pick(info, "download_url", "downloadUrl", "video_url", "videoUrl"))
        if not url:
            raise RuntimeError("视频接口没有可下载地址")
        return {"status": "ok", "url": url, "data": info}
    except Exception as exc:
        logger.error(f"解析视频地址失败: {exc}")
        return {"status": "error", "message": str(exc)}


class ApiAlbum(ApiBase):
    album_list_url = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/fcg_list_album_v3"
    photo_list_url = "https://user.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/cgi_list_photo"
    video_info_url = "https://h5.qzone.qq.com/proxy/domain/photo.qzone.qq.com/fcgi-bin/cgi_floatview_photo_list_v2"

    def _cookies_with_photo_key(self, cookies: str) -> str:
        key = getattr(self, "_qq_photo_key", "")
        if not key or re.search(r"(?:^|;\s*)qq_photo_key=", cookies):
            return cookies
        return f"{cookies}; qq_photo_key={key}"

    def album_media_cookies(self, cookies: str) -> str:
        """返回包含相册接口临时 qq_photo_key 的媒体下载 Cookie。"""
        return self._cookies_with_photo_key(cookies)

    def _capture_photo_key(self, headers: Dict[str, List[str]]) -> None:
        for raw in headers.get("set-cookie", []):
            jar = SimpleCookie()
            try:
                jar.load(raw)
            except Exception:
                continue
            if "qq_photo_key" in jar:
                self._qq_photo_key = jar["qq_photo_key"].value
                return

    async def get_album_list(
        self,
        target_qq: int,
        g_tk: int,
        cookies: str,
        page: int = 0,
        count: int = 30,
        login_qq: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        operator = login_qq or target_qq
        content = await self._make_get_request(
            self.album_list_url,
            get_album_list(target_qq, operator, g_tk, page, count),
            cookies,
            referer=f"https://user.qzone.qq.com/{operator}/infocenter",
        )
        return parse_album_list(content) if content else None

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
        operator = login_qq or target_qq
        active_cookies = self._cookies_with_photo_key(cookies)
        result = await self._make_get_request_with_meta(
            self.photo_list_url,
            get_album_photos(target_qq, operator, album_id, g_tk, start, count),
            active_cookies,
            referer=f"https://user.qzone.qq.com/{target_qq}/4",
        )
        if not result:
            return None
        content, headers = result
        self._capture_photo_key(headers)
        return parse_photo_list(content)

    async def get_video_download_url(
        self,
        target_qq: int,
        album_id: str,
        sloc: str,
        g_tk: int,
        cookies: str,
        login_qq: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        operator = login_qq or target_qq
        content = await self._make_get_request(
            self.video_info_url,
            get_video_info(target_qq, operator, album_id, sloc, g_tk),
            self._cookies_with_photo_key(cookies),
            referer=f"https://user.qzone.qq.com/{target_qq}/infocenter",
        )
        return parse_video_info(content) if content else None


__all__ = [
    "ApiAlbum",
    "parse_album_list",
    "parse_photo_list",
    "parse_video_info",
]
