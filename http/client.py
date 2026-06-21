"""
HTTP Client - Async HTTP requests with health tracking
Pattern: Centralized HTTP client with retry logic
"""
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime


class HttpClient:
    """
    Async HTTP client with automatic retry and health tracking.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize HTTP client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            retry_delay: Delay between retries in seconds
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: Optional[aiohttp.ClientSession] = None
        self._health_stats: Dict[str, Dict[str, Any]] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _track_request(
        self,
        url: str,
        success: bool,
        latency_ms: float
    ) -> None:
        """Track request health metrics"""
        if url not in self._health_stats:
            self._health_stats[url] = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "total_latency_ms": 0,
                "last_request": None
            }

        stats = self._health_stats[url]
        stats["total_requests"] += 1
        stats["total_latency_ms"] += latency_ms
        stats["last_request"] = datetime.now().isoformat()

        if success:
            stats["successful_requests"] += 1
        else:
            stats["failed_requests"] += 1

    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make GET request with retry logic.

        Args:
            url: Request URL
            headers: Request headers
            params: Query parameters
            **kwargs: Additional aiohttp parameters

        Returns:
            Response data

        Raises:
            Exception: If all retries fail
        """
        session = await self._get_session()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                start_time = asyncio.get_event_loop().time()

                async with session.get(
                    url,
                    headers=headers,
                    params=params,
                    **kwargs
                ) as response:
                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                    if response.status >= 500:
                        raise Exception(f"Server error: {response.status}")

                    if response.status >= 400:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")

                    data = await response.json()
                    self._track_request(url, True, latency_ms)
                    return data

            except Exception as e:
                last_error = e
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                self._track_request(url, False, latency_ms)

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise last_error or Exception("Request failed")

    async def post(
        self,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make POST request with retry logic.

        Args:
            url: Request URL
            json_data: JSON body
            data: Form data
            headers: Request headers
            **kwargs: Additional aiohttp parameters

        Returns:
            Response data

        Raises:
            Exception: If all retries fail
        """
        session = await self._get_session()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                start_time = asyncio.get_event_loop().time()

                async with session.post(
                    url,
                    json=json_data,
                    data=data,
                    headers=headers,
                    **kwargs
                ) as response:
                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                    if response.status >= 500:
                        raise Exception(f"Server error: {response.status}")

                    if response.status >= 400:
                        error_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {error_text}")

                    resp_data = await response.json()
                    self._track_request(url, True, latency_ms)
                    return resp_data

            except Exception as e:
                last_error = e
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                self._track_request(url, False, latency_ms)

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise last_error or Exception("Request failed")

    async def get_text(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> str:
        """
        Make GET request and return text response.

        Args:
            url: Request URL
            headers: Request headers
            **kwargs: Additional parameters

        Returns:
            Response text
        """
        session = await self._get_session()

        async with session.get(url, headers=headers, **kwargs) as response:
            if response.status >= 400:
                raise Exception(f"HTTP {response.status}")
            return await response.text()

    def get_health_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get health statistics for all URLs.

        Returns:
            Health stats dict
        """
        stats = {}

        for url, data in self._health_stats.items():
            total = data["total_requests"]
            successful = data["successful_requests"]

            stats[url] = {
                "total_requests": total,
                "successful_requests": successful,
                "failed_requests": data["failed_requests"],
                "success_rate": round(successful / total * 100, 2) if total > 0 else 100,
                "avg_latency_ms": round(data["total_latency_ms"] / total, 2) if total > 0 else 0,
                "last_request": data["last_request"]
            }

        return stats
