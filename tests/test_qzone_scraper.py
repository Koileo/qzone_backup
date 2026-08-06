import asyncio
import json
import base64
import functools
import http.server
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

from qzone_scraper import (
    build_snapshot,
    download_snapshot_media,
    normalise_qq,
    render_archive_html,
    save_archive_html,
    save_snapshot,
    scrape_albums,
    scrape_messages,
)


class FakeApi:
    def __init__(self):
        self.calls = []

    async def get_messages_list(self, target_qq, g_tk, cookies, pos=0, num=20):
        self.calls.append((target_qq, g_tk, cookies, pos, num))
        pages = {
            0: [{"cur_key": "a", "content": "第一条"}, {"cur_key": "b", "content": "第二条"}],
            2: [{"cur_key": "b", "content": "重复"}],
        }
        return {"status": "ok", "data": pages.get(pos, [])}


class FakeAlbumApi:
    def __init__(self):
        self.photo_starts = []
        self.video_calls = []

    async def get_album_list(self, target_qq, g_tk, cookies, page=0, count=100, login_qq=None):
        return {
            "status": "ok",
            "data": [
                {"id": "album-a", "name": "旅行", "photo_count": 3, "allow_access": 1},
                {"id": "album-b", "name": "私密", "photo_count": 4, "allow_access": 0},
            ],
        }

    async def get_album_photos(
        self, target_qq, album_id, g_tk, cookies, start=0, count=100, login_qq=None
    ):
        self.photo_starts.append(start)
        pages = {
            0: [{"id": "p1", "url": "https://example/p1.jpg"}, {"id": "p2", "url": "https://example/p2.jpg"}],
            2: [
                {
                    "id": "p3",
                    "url": "https://example/p3.jpg",
                    "is_video": True,
                    "sloc": "video-key",
                }
            ],
        }
        return {"status": "ok", "total": 3, "data": pages.get(start, [])}

    async def get_video_download_url(
        self, target_qq, album_id, sloc, g_tk, cookies, login_qq=None
    ):
        self.video_calls.append((target_qq, login_qq, album_id, sloc))
        return {"status": "ok", "url": "https://example/video.mp4"}


class PagedAlbumApi:
    def __init__(self):
        self.pages = []

    async def get_album_list(self, target_qq, g_tk, cookies, page=0, count=30, login_qq=None):
        self.pages.append((page, target_qq, login_qq))
        if page == 0:
            return {
                "status": "ok",
                "total_available": 2,
                "next_start": 30,
                "data": [{"id": "a", "name": "A", "allow_access": 0}],
            }
        return {
            "status": "ok",
            "total_available": 2,
            "next_start": 60,
            "data": [{"id": "b", "name": "B", "allow_access": 0}],
        }

    async def get_album_photos(self, *args, **kwargs):
        raise AssertionError("锁定相册不应请求照片")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class ScraperTests(unittest.TestCase):
    def test_normalise_qq(self):
        self.assertEqual(normalise_qq("o123"), 123)
        self.assertEqual(normalise_qq(456), 456)
        with self.assertRaises(ValueError):
            normalise_qq("abc")

    def test_scrape_deduplicates_and_stops_on_short_page(self):
        api = FakeApi()
        feeds = asyncio.run(scrape_messages(api, 123, 456, "sid=x", page_size=2, delay=0))
        self.assertEqual([item["cur_key"] for item in feeds], ["a", "b"])
        self.assertEqual([call[3] for call in api.calls], [0, 2])

    def test_save_snapshot_is_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = save_snapshot(build_snapshot(123, [{"content": "你好"}]), Path(directory) / "data.json")
            with path.open(encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertEqual(saved["total"], 1)
            self.assertEqual(saved["data"][0]["content"], "你好")

    def test_scrape_albums_paginates_and_keeps_locked_album(self):
        api = FakeAlbumApi()
        albums = asyncio.run(
            scrape_albums(api, 123, 456, "sid=x", login_qq=999, photo_page_size=2, delay=0)
        )
        self.assertEqual(api.photo_starts, [0, 2])
        self.assertEqual([photo["id"] for photo in albums[0]["photos"]], ["p1", "p2", "p3"])
        self.assertEqual(albums[0]["photos"][2]["video_url"], "https://example/video.mp4")
        self.assertEqual(api.video_calls, [(123, 999, "album-a", "video-key")])
        self.assertEqual(albums[1]["photos"], [])

    def test_album_list_uses_server_cursor_and_name_filter(self):
        api = PagedAlbumApi()
        albums = asyncio.run(
            scrape_albums(
                api,
                123,
                456,
                "sid=x",
                login_qq=999,
                album_names=["B"],
                delay=0,
            )
        )
        self.assertEqual(api.pages, [(0, 123, 999), (30, 123, 999)])
        self.assertEqual([album["name"] for album in albums], ["B"])

    def test_download_media_and_render_offline_html(self):
        pixel = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "photo.png").write_bytes(pixel)
            (source / "video.mp4").write_bytes(b"fixture-video")
            handler = functools.partial(QuietHandler, directory=str(source))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/photo.png"
                video_url = f"http://127.0.0.1:{server.server_port}/video.mp4"
                snapshot = build_snapshot(
                    123,
                    [{"cur_key": "mood/1", "content": "<script>alert(1)</script>", "images": [{"url": url}]}],
                    [
                        {
                            "id": "album/1",
                            "name": "夏日",
                            "cover_url": url,
                            "photos": [
                                {"id": "p1", "url": url, "captured_time": 1_700_000_000},
                                {"id": "p2", "sloc": "stable-video", "video_url": video_url, "is_video": True},
                            ],
                        }
                    ],
                )
                copied, report = asyncio.run(
                    download_snapshot_media(snapshot, root / "archive" / "media", concurrency=2)
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertEqual(report, {"downloaded": 4, "skipped": 0, "failed": 0})
            mood_path = copied["data"][0]["images"][0]["local_path"]
            album_path = copied["albums"][0]["photos"][0]["local_path"]
            video_path = copied["albums"][0]["photos"][1]["local_path"]
            self.assertTrue((root / "archive" / mood_path).is_file())
            self.assertTrue((root / "archive" / album_path).is_file())
            self.assertTrue((root / "archive" / video_path).is_file())
            self.assertTrue(video_path.endswith(".mp4"))
            self.assertIn("夏日--album-1", album_path)
            expected_month = datetime.fromtimestamp(1_700_000_000).strftime("%Y/%m")
            self.assertIn(f"/{expected_month}/", album_path)
            self.assertIn("/未分类/", video_path)
            self.assertEqual(int((root / "archive" / album_path).stat().st_mtime), 1_700_000_000)
            self.assertNotIn("local_path", snapshot["data"][0]["images"][0])

            html = render_archive_html(copied)
            self.assertIn("空间档案", html)
            self.assertIn("相册底片册", html)
            self.assertIn(mood_path, html)
            self.assertIn("<video", html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertNotIn("<script>alert(1)</script>", html)
            html_path = save_archive_html(copied, root / "archive" / "index.html")
            self.assertTrue(html_path.is_file())

            retry_snapshot = build_snapshot(
                123,
                [],
                [
                    {
                        "id": "album/1",
                        "name": "夏日",
                        "photos": [
                            {
                                "id": "p2",
                                "sloc": "stable-video",
                                "video_url": video_url + "?new-token=1",
                                "is_video": True,
                            }
                        ],
                    }
                ],
            )
            retried, retry_report = asyncio.run(
                download_snapshot_media(retry_snapshot, root / "archive" / "media", concurrency=1)
            )
            self.assertEqual(retry_report["skipped"], 1)
            self.assertEqual(retried["albums"][0]["photos"][0]["local_path"], video_path)


class TargetParsingTests(unittest.TestCase):
    def test_multiple_targets_are_deduplicated(self):
        from main import _target_list

        self.assertEqual(_target_list(["123,456", "o123"], 999), [123, 456])
        self.assertEqual(_target_list(None, 999), [999])

    def test_mode_specific_html_hides_unrequested_section(self):
        mood_html = render_archive_html(build_snapshot(123, [], included=["moods"]))
        album_html = render_archive_html(build_snapshot(123, [], [], included=["albums"]))
        self.assertIn("说说时间线", mood_html)
        self.assertNotIn("相册底片册", mood_html)
        self.assertIn("相册底片册", album_html)
        self.assertNotIn("说说时间线", album_html)


if __name__ == "__main__":
    unittest.main()
