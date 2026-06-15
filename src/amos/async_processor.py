"""Async processing module for AMOS memory processing.

This module provides background processing capabilities to decouple
expensive operations (like LLM inference) from the main request path.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .service import Amos

logger = logging.getLogger(__name__)


class ProcessingStatus(Enum):
    """Status of async memory processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProcessingTask:
    """A task for async memory processing."""
    tenant_id: str
    memory_id: str
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: ProcessingStatus = ProcessingStatus.PENDING
    error: str | None = None
    retry_count: int = 0


class AsyncProcessor:
    """Background processor for memory processing tasks.
    
    Uses a thread-based queue to process memories asynchronously,
    allowing the main request path to return immediately while
    expensive operations (LLM inference, extraction) happen in the background.
    
    Features:
    - Non-blocking memory storage
    - Background worker thread
    - Status tracking
    - Error handling and retry logic
    - Graceful shutdown
    """

    def __init__(
        self,
        amos: Amos,
        *,
        num_workers: int = 1,
        max_retries: int = 3,
        queue_size: int = 1000,
    ) -> None:
        """Initialize async processor.
        
        Args:
            amos: AMOS instance to use for processing
            num_workers: Number of worker threads (default: 1)
            max_retries: Maximum retry attempts for failed tasks (default: 3)
            queue_size: Maximum queue size (default: 1000)
        """
        self.amos = amos
        self.num_workers = num_workers
        self.max_retries = max_retries
        self.queue: Queue[ProcessingTask] = Queue(maxsize=queue_size)
        self.status_cache: dict[str, ProcessingTask] = {}
        self.workers: list[threading.Thread] = []
        self.running = False
        self.stats = {
            "total_queued": 0,
            "total_processed": 0,
            "total_failed": 0,
            "total_retried": 0,
        }
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start worker threads."""
        if self.running:
            logger.warning("AsyncProcessor already running")
            return

        self.running = True
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"amos-worker-{i}",
                daemon=True,
            )
            worker.start()
            self.workers.append(worker)
        logger.info(f"Started {self.num_workers} async processing workers")

    def stop(self, timeout: float = 30.0) -> None:
        """Stop worker threads gracefully.
        
        Args:
            timeout: Maximum time to wait for workers to finish (seconds)
        """
        if not self.running:
            return

        logger.info("Stopping async processor...")
        self.running = False

        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=timeout / len(self.workers))

        # Log remaining queue items
        remaining = self.queue.qsize()
        if remaining > 0:
            logger.warning(f"{remaining} tasks remaining in queue")

        logger.info("Async processor stopped")

    def queue_processing(
        self,
        tenant_id: str,
        memory_id: str,
    ) -> ProcessingTask:
        """Queue a memory for async processing.
        
        Args:
            tenant_id: Tenant ID
            memory_id: Memory ID to process
            
        Returns:
            ProcessingTask with status tracking
            
        Raises:
            RuntimeError: If processor is not running
            ValueError: If queue is full
        """
        if not self.running:
            raise RuntimeError("AsyncProcessor not started. Call start() first.")

        task = ProcessingTask(
            tenant_id=tenant_id,
            memory_id=memory_id,
            queued_at=datetime.now(timezone.utc),
        )

        try:
            self.queue.put_nowait(task)
            with self._lock:
                self.status_cache[f"{tenant_id}:{memory_id}"] = task
                self.stats["total_queued"] += 1
            logger.debug(f"Queued processing for memory {memory_id}")
            return task
        except Exception as e:
            logger.error(f"Failed to queue task: {e}")
            raise ValueError(f"Queue is full (max: {self.queue.maxsize})") from e

    def get_status(self, tenant_id: str, memory_id: str) -> ProcessingTask | None:
        """Get processing status for a memory.
        
        Args:
            tenant_id: Tenant ID
            memory_id: Memory ID
            
        Returns:
            ProcessingTask if found, None otherwise
        """
        cache_key = f"{tenant_id}:{memory_id}"
        with self._lock:
            return self.status_cache.get(cache_key)

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self.queue.qsize()

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics."""
        with self._lock:
            return {
                **self.stats,
                "queue_size": self.queue.qsize(),
                "workers": self.num_workers,
                "running": self.running,
            }

    def _worker_loop(self) -> None:
        """Main worker loop - processes tasks from queue."""
        logger.info(f"Worker {threading.current_thread().name} started")

        while self.running:
            try:
                # Get task with timeout to allow checking running flag
                task = self.queue.get(timeout=1.0)
            except Empty:
                continue

            try:
                self._process_task(task)
            except Exception as e:
                logger.error(f"Unexpected error processing task: {e}", exc_info=True)
                self._mark_failed(task, str(e))
            finally:
                self.queue.task_done()

        logger.info(f"Worker {threading.current_thread().name} stopped")

    def _process_task(self, task: ProcessingTask) -> None:
        """Process a single task.
        
        Args:
            task: Task to process
        """
        cache_key = f"{task.tenant_id}:{task.memory_id}"

        # Update status to processing
        task.status = ProcessingStatus.PROCESSING
        task.started_at = datetime.now(timezone.utc)
        with self._lock:
            self.status_cache[cache_key] = task

        try:
            # Perform the actual processing
            logger.debug(f"Processing memory {task.memory_id}")
            self.amos.process_memory(
                tenant_id=task.tenant_id,
                memory_id=task.memory_id,
                force=False,
            )

            # Mark as completed
            task.status = ProcessingStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            with self._lock:
                self.status_cache[cache_key] = task
                self.stats["total_processed"] += 1

            logger.debug(f"Completed processing memory {task.memory_id}")

        except Exception as e:
            logger.error(f"Failed to process memory {task.memory_id}: {e}")

            # Retry logic
            if task.retry_count < self.max_retries:
                task.retry_count += 1
                task.status = ProcessingStatus.PENDING
                with self._lock:
                    self.stats["total_retried"] += 1
                logger.info(f"Retrying memory {task.memory_id} (attempt {task.retry_count}/{self.max_retries})")
                self.queue.put(task)
            else:
                self._mark_failed(task, str(e))

    def _mark_failed(self, task: ProcessingTask, error: str) -> None:
        """Mark a task as failed.
        
        Args:
            task: Task that failed
            error: Error message
        """
        task.status = ProcessingStatus.FAILED
        task.error = error
        task.completed_at = datetime.now(timezone.utc)

        cache_key = f"{task.tenant_id}:{task.memory_id}"
        with self._lock:
            self.status_cache[cache_key] = task
            self.stats["total_failed"] += 1

        logger.error(f"Task failed permanently: {task.memory_id} - {error}")

    def clear_completed(self, older_than_seconds: int = 3600) -> int:
        """Clear completed tasks from status cache.
        
        Args:
            older_than_seconds: Clear tasks completed more than this many seconds ago
            
        Returns:
            Number of tasks cleared
        """
        now = datetime.now(timezone.utc)
        cleared = 0

        with self._lock:
            keys_to_remove = []
            for key, task in self.status_cache.items():
                if (
                    task.status in (ProcessingStatus.COMPLETED, ProcessingStatus.FAILED)
                    and task.completed_at
                    and (now - task.completed_at).total_seconds() > older_than_seconds
                ):
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self.status_cache[key]
                cleared += 1

        if cleared > 0:
            logger.info(f"Cleared {cleared} completed tasks from cache")

        return cleared

