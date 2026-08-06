"""Resource management for HTTP sessions, worker pools, and global CPU semaphores."""

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable
from typing import Any

from storage import storage

logger = logging.getLogger(__name__)


class ResourceManager:
    """Manages process/thread executor pools, global CPU semaphores, and HTTP sessions cleanly."""

    def __init__(self):
        self._http_session: Any | None = None
        self._process_pool: concurrent.futures.ProcessPoolExecutor | None = None
        self._cpu_pool: concurrent.futures.ThreadPoolExecutor | None = None
        self._cpu_semaphore: asyncio.Semaphore | None = None

    async def get_http_session(self) -> Any:
        import aiohttp
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=60)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    async def close_http_session(self):
        if self._http_session is not None and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None
            logger.info("HTTP session closed cleanly.")

    def get_process_pool(self) -> concurrent.futures.ProcessPoolExecutor:
        workers = storage.get("process_pool_workers", 1)
        if self._process_pool is None:
            self._process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=workers)
            logger.info(f"ProcessPoolExecutor created with max_workers={workers}")
        return self._process_pool

    def rebuild_process_pool(self, workers: int):
        """Rebuild process pool safely. Wait for existing in-flight jobs to complete before replacement."""
        old_pool = self._process_pool
        self._process_pool = concurrent.futures.ProcessPoolExecutor(max_workers=workers)
        logger.info(f"ProcessPoolExecutor rebuilt with max_workers={workers}")
        if old_pool is not None:
            try:
                old_pool.shutdown(wait=True, cancel_futures=False)
            except Exception as e:
                logger.warning(f"Error shutting down old ProcessPoolExecutor: {e}")

    def get_cpu_pool(self) -> concurrent.futures.ThreadPoolExecutor:
        workers = storage.get("max_concurrent", 2)
        if self._cpu_pool is None:
            self._cpu_pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
            logger.info(f"CPU ThreadPoolExecutor created with max_workers={workers}")
        return self._cpu_pool

    def rebuild_cpu_pool(self, workers: int):
        """Rebuild CPU thread pool safely and update global CPU semaphore."""
        old_pool = self._cpu_pool
        self._cpu_pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        self._cpu_semaphore = asyncio.Semaphore(workers)
        logger.info(f"CPU ThreadPoolExecutor rebuilt with max_workers={workers}")
        if old_pool is not None:
            try:
                old_pool.shutdown(wait=True, cancel_futures=False)
            except Exception as e:
                logger.warning(f"Error shutting down old ThreadPoolExecutor: {e}")

    def get_cpu_semaphore(self) -> asyncio.Semaphore:
        """Global concurrency semaphore shared across all CPU-bound operations."""
        workers = storage.get("max_concurrent", 2)
        if self._cpu_semaphore is None:
            self._cpu_semaphore = asyncio.Semaphore(workers)
        return self._cpu_semaphore

    async def run_cpu_bound(self, func: Callable, *args) -> Any:
        """Run CPU-heavy sync work in worker thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.get_cpu_pool(), lambda: func(*args))

    async def shutdown(self):
        """Clean shutdown of all pools and sessions."""
        await self.close_http_session()
        if self._process_pool is not None:
            self._process_pool.shutdown(wait=True, cancel_futures=True)
            self._process_pool = None
        if self._cpu_pool is not None:
            self._cpu_pool.shutdown(wait=True, cancel_futures=True)
            self._cpu_pool = None
        self._cpu_semaphore = None
        logger.info("ResourceManager shutdown complete.")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()


# Global default instance
resources = ResourceManager()
