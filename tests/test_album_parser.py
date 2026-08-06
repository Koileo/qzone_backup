import asyncio
import json
import unittest

from qzone_api.api.api_album import ApiAlbum, parse_album_list, parse_photo_list, parse_video_info
from qzone_api.api.api_parms import get_album_list, get_album_photos


class FakeTransportAlbum(ApiAlbum):
    def __init__(self):
        self.calls = []

    async def _make_get_request_with_meta(self, url, params, cookies, referer=""):
        self.calls.append((url, params, cookies, referer))
        payload = json.dumps({"code": 0, "data": {"photoList": [], "totalInAlbum": 0}})
        return f"shine_Callback({payload});", {
            "set-cookie": ["qq_photo_key=transport-key; Path=/; Secure"]
        }


class AlbumParserTests(unittest.TestCase):
    def test_parses_jsonp_album_fields(self):
        payload = {
            "code": 0,
            "data": {
                "albumListModeSort": [
                    {
                        "id": "a1",
                        "name": "旅行",
                        "desc": "海边",
                        "coverurl": "https://example/cover.jpg",
                        "picnum": "12",
                        "allowAccess": 1,
                    }
                ]
            },
        }
        parsed = parse_album_list(f"shine0_Callback({json.dumps(payload)});")
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["data"][0]["photo_count"], 12)
        self.assertEqual(parsed["data"][0]["name"], "旅行")

    def test_parses_real_album_pagination_shape(self):
        payload = {
            "code": 0,
            "data": {
                "albumList": [{"id": "a1", "name": "旅行", "total": 8}],
                "nextPageStart": 30,
                "albumsInUser": 42,
            },
        }
        parsed = parse_album_list(f"shine_Callback({json.dumps(payload)});")
        self.assertEqual(parsed["data"][0]["photo_count"], 8)
        self.assertEqual(parsed["next_start"], 30)
        self.assertEqual(parsed["total_available"], 42)

    def test_prefers_original_photo_url(self):
        payload = {
            "code": 0,
            "data": {
                "totalInAlbum": 1,
                "photoList": [
                    {
                        "id": "p1",
                        "origin_url": "https://example/original.jpg",
                        "pre": "https://example/preview.jpg",
                        "width": 1920,
                        "height": 1080,
                    }
                ],
            },
        }
        parsed = parse_photo_list(json.dumps(payload))
        self.assertEqual(parsed["total"], 1)
        self.assertEqual(parsed["data"][0]["url"], "https://example/original.jpg")

    def test_photo_preserves_raw_video_and_capture_time(self):
        payload = {
            "code": 0,
            "data": {
                "totalInAlbum": 1,
                "photoList": [
                    {
                        "id": "p1",
                        "sloc": "video-key",
                        "raw": "https://example/photo?b&bo=x",
                        "rawshoottime": "2024-02-03 04:05:06",
                        "uploadtime": "2024-02-04 04:05:06",
                        "is_video": 1,
                    }
                ],
            },
        }
        photo = parse_photo_list(json.dumps(payload))["data"][0]
        self.assertIn("o&bo=", photo["url"])
        self.assertEqual(photo["sloc"], "video-key")
        self.assertTrue(photo["is_video"])
        self.assertGreater(photo["captured_time"], 0)

    def test_operator_and_target_uin_are_distinct(self):
        album_params = get_album_list(222, 111, 333, start=30, count=20)
        photo_params = get_album_photos(222, 111, "album", 333, start=500, count=500)
        self.assertEqual(album_params["hostUin"], 222)
        self.assertEqual(album_params["uin"], 111)
        self.assertEqual(album_params["pageStart"], 30)
        self.assertEqual(photo_params["hostUin"], 222)
        self.assertEqual(photo_params["uin"], 111)

    def test_photo_key_is_reused(self):
        api = ApiAlbum()
        api._capture_photo_key({"set-cookie": ["qq_photo_key=fixture-key; Path=/; Secure"]})
        self.assertIn("qq_photo_key=fixture-key", api._cookies_with_photo_key("skey=x"))
        self.assertIn("qq_photo_key=fixture-key", api.album_media_cookies("skey=x"))

    def test_video_url_parser(self):
        payload = {
            "code": 0,
            "data": {
                "picPosInPage": 0,
                "photos": [{"video_info": {"download_url": "https://example/video.mp4"}}],
            },
        }
        parsed = parse_video_info(f"viewer_Callback({json.dumps(payload)});")
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["url"], "https://example/video.mp4")

    def test_photo_request_captures_and_reuses_response_cookie(self):
        api = FakeTransportAlbum()

        async def exercise():
            await api.get_album_photos(222, "album", 333, "skey=x", login_qq=111)
            await api.get_album_photos(222, "album", 333, "skey=x", login_qq=111)

        asyncio.run(exercise())
        self.assertEqual(api.calls[0][1]["hostUin"], 222)
        self.assertEqual(api.calls[0][1]["uin"], 111)
        self.assertNotIn("qq_photo_key", api.calls[0][2])
        self.assertIn("qq_photo_key=transport-key", api.calls[1][2])
        self.assertTrue(api.calls[0][3].endswith("/222/4"))


if __name__ == "__main__":
    unittest.main()
