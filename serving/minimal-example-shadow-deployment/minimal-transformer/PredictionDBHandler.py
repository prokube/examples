import asyncio
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from logging import shutdown
from typing import Dict, List

import asyncpg

logger = logging.getLogger(__name__)


class PredictionDBHandler:
    def __init__(
        self,
        db_url: str,
        response_table_name: str = "inference_response",
        request_table_name: str = "inference_requests",
    ):
        self.db_url = db_url
        self.response_table_name = response_table_name
        self.request_table_name = request_table_name

        self.request_query, self.response_query = self.initialize_database_table()

        self.pool = None
        self.batch_size = 50
        self.batch_timeout = 5.0  # seconds

        logger.debug(
            "Initials queue with %d elements and timout of %d seconds",
            self.batch_size,
            self.batch_timeout,
        )

        self.prediction_queue = []
        self.queue_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.running = True
        self.batch_worker = threading.Thread(target=self._run_batch_worker)
        self.batch_worker.daemon = True
        self.batch_worker.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    def initialize_database_table(self):
        request_query = f"""INSERT INTO {self.request_table_name}(request_id,request_time,request_data,predict_url,created_at)VALUES($1,$2,$3,$4, NOW())"""
        response_query = f"""INSERT INTO {self.response_table_name}(request_id,response_data,created_at) VALUES($1,$2, NOW())"""

        return request_query, response_query

    async def initialize_pool(self):
        self.pool = await asyncpg.create_pool(self.db_url)

        # Don't print user credentials
        database_uri = self.db_url.split("@")[-1]
        logger.debug("Connection pool connected to %s", database_uri)

    def queue_request(self, request_id, request_time, predict_url, request_data):
        with self.queue_lock:
            self.prediction_queue.append(
                (
                    self.request_query,
                    request_id,
                    request_time,
                    request_data,
                    predict_url,
                )
            )

    def queue_response(self, request_id, response_data):
        with self.queue_lock:
            self.prediction_queue.append(
                (
                    self.response_query,
                    request_id,
                    response_data,
                )
            )

    def _run_batch_worker(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.initialize_pool())
        last_flushed_time = time.time()
        while self.running:
            # Sleep briefly to avoid CPU spinning
            time.sleep(0.1)
            current_time = time.time()
            # Check if we have enough items or if it's time to flush
            should_process = False
            current_batch = []
            with self.queue_lock:
                if (
                    len(self.prediction_queue) >= self.batch_size
                    or len(self.prediction_queue) > 0
                    and (current_time - last_flushed_time) >= self.batch_timeout
                ):
                    current_batch = self.prediction_queue[: self.batch_size]
                    self.prediction_queue = self.prediction_queue[self.batch_size :]
                    should_process = True

            if should_process and current_batch:
                loop.run_until_complete(self.store_batch(current_batch))
                last_flushed_time = current_time

    async def store_batch(self, batch):
        if not batch:
            return
        try:
            async with self.pool.acquire() as con:
                for query in batch:
                    logger.debug("Send query: %s", query)
                    await con.execute(*query)

        except Exception as e:
            logger.error("Database error: %s", e)

    def shutdown(self):
        self.running = False
        # Process any remaining items
        loop = asyncio.get_event_loop()
        with self.queue_lock:
            if self.prediction_queue:
                loop.run_until_complete(self.store_batch(self.prediction_queue))
        # Close pool
        if self.pool:
            loop.run_until_complete(self.pool.close())
