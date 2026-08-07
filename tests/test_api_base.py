import unittest
from unittest.mock import AsyncMock, patch

from qzone_api.api.api_base import ApiBase


class FakeHeaders(dict):
    def getall(self, key, default=None):
        return [self[key]] if key in self else (default or [])


class FakeResponse:
    def __init__(self, status, body="", headers=None):
        self.status = status
        self.body = body
        self.headers = FakeHeaders(headers or {})

    async def text(self):
        return self.body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return next(self.responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class ApiBaseRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_501_retries_same_request(self):
        session = FakeSession([FakeResponse(501), FakeResponse(200, "fixture")])
        sleep = AsyncMock()
        with patch("qzone_api.api.api_base.aiohttp.ClientSession", return_value=session), patch(
            "qzone_api.api.api_base.asyncio.sleep", sleep
        ):
            result = await ApiBase()._make_get_request("https://example.test", {"pos": 1580}, "sid=x")

        self.assertEqual(result, "fixture")
        self.assertEqual(session.calls, 2)
        sleep.assert_awaited_once_with(1)

    async def test_non_transient_status_is_not_retried(self):
        session = FakeSession([FakeResponse(403)])
        with patch("qzone_api.api.api_base.aiohttp.ClientSession", return_value=session):
            result = await ApiBase()._make_get_request("https://example.test", {}, "sid=x")

        self.assertIsNone(result)
        self.assertEqual(session.calls, 1)

    async def test_exhausted_501_suggests_waiting_or_changing_ip(self):
        session = FakeSession([FakeResponse(501) for _ in range(5)])
        sleep = AsyncMock()
        with patch("qzone_api.api.api_base.aiohttp.ClientSession", return_value=session), patch(
            "qzone_api.api.api_base.asyncio.sleep", sleep
        ), patch("qzone_api.api.api_base.logger.error") as log_error:
            result = await ApiBase()._make_get_request("https://example.test", {}, "sid=x")

        self.assertIsNone(result)
        self.assertEqual(session.calls, 5)
        log_error.assert_called_once_with(
            "请求失败状态码: 501。服务当前可能繁忙或限制了请求，"
            "建议过一会儿再来爬取，或者更换 IP 后重试。"
        )


if __name__ == "__main__":
    unittest.main()
