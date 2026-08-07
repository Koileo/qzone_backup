import asyncio
import aiohttp
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

class ApiBase:
    _TRANSIENT_GET_STATUSES = {429, 500, 501, 502, 503, 504}
    _MAX_GET_ATTEMPTS = 5

    async def _make_post_request(self, url: str, data: Dict[str, Any], cookies: str, content_type: str = 'application/x-www-form-urlencoded') -> Optional[Dict[str, Any]]:
        """通用POST请求方法"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": cookies,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": content_type,
            "Origin": "https://user.qzone.qq.com",
            "Referer": "https://user.qzone.qq.com/"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        content = await response.text()
                        logger.debug(f"POST响应内容: {content[:100]}")
                        if 'text/html' in response.headers.get('Content-Type', ''):
                            match = re.search(r'({.*})', content)
                            if match:
                                try:
                                    return json.loads(match.group(1))
                                except json.JSONDecodeError:
                                    pass
                            match = re.search(r'_Callback\((.*)\);', content)
                            if match:
                                try:
                                    return json.loads(match.group(1))
                                except json.JSONDecodeError:
                                    pass
                        return content
                    logger.error(f"POST请求失败: {response.status}")
                    return None  
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return None

    async def _make_get_request_with_meta(
        self,
        url: str,
        params: Dict[str, Any],
        cookies: str,
        referer: str = "https://user.qzone.qq.com/",
    ) -> Optional[Tuple[str, Dict[str, List[str]]]]:
        """GET 请求并保留响应头，供相册接口读取 Set-Cookie。"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": cookies,
            "Accept": "application/json, text/plain, */*",
            "Referer": referer,
            "Origin": "https://user.qzone.qq.com",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                for attempt in range(1, self._MAX_GET_ATTEMPTS + 1):
                    retry_delay = 0.0
                    try:
                        async with session.get(url, params=params, headers=headers) as response:
                            if response.status == 200:
                                content = await response.text()
                                logger.debug(f"GET响应成功: {response.status}, {len(content)} bytes")
                                response_headers = {
                                    key.lower(): response.headers.getall(key, [])
                                    for key in response.headers.keys()
                                }
                                return content, response_headers

                            if (
                                response.status in self._TRANSIENT_GET_STATUSES
                                and attempt < self._MAX_GET_ATTEMPTS
                            ):
                                retry_after = response.headers.get("Retry-After")
                                try:
                                    retry_delay = max(float(retry_after), 0.0)
                                except (TypeError, ValueError):
                                    retry_delay = min(2 ** (attempt - 1), 8)
                                logger.warning(
                                    f"请求失败状态码: {response.status}，{retry_delay:g} 秒后重试 "
                                    f"({attempt}/{self._MAX_GET_ATTEMPTS})"
                                )
                            else:
                                logger.error(f"请求失败状态码: {response.status}")
                                return None
                    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                        if attempt >= self._MAX_GET_ATTEMPTS:
                            logger.error(f"请求异常，已用完重试次数: {exc}")
                            return None
                        retry_delay = min(2 ** (attempt - 1), 8)
                        logger.warning(
                            f"请求异常: {exc}，{retry_delay:g} 秒后重试 "
                            f"({attempt}/{self._MAX_GET_ATTEMPTS})"
                        )

                    await asyncio.sleep(retry_delay)
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return None

    async def _make_get_request(
        self,
        url: str,
        params: Dict[str, Any],
        cookies: str,
        referer: str = "https://user.qzone.qq.com/",
    ) -> Optional[str]:
        """通用 GET 请求方法。"""
        result = await self._make_get_request_with_meta(url, params, cookies, referer)
        return result[0] if result else None
