import asyncio
import os
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.config import settings
from app.schemas import PipelineParams, JobResponse

logger = logging.getLogger(__name__)


class Job:
    def __init__(self, job_id: str, params: PipelineParams, image_bytes: bytes):
        self.id = job_id
        self.params = params
        self.image_bytes = image_bytes
        self.status: str = "queued"
        self.stage: str = "queued"
        self.progress: float = 0.0
        self.queue_position: int = 0
        self.error: Optional[str] = None
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.updated_at: float = time.time()
        self.future: Optional[Future] = None
        self.warnings: list[str] = []

        # Artifacts
        self.svg_data: Optional[bytes] = None
        self.png_data: Optional[bytes] = None
        self.report_data: Optional[dict] = None

    def to_response(self, queue_position: int = 0) -> JobResponse:
        return JobResponse(
            id=self.id,
            status=self.status,
            stage=self.stage,
            progress=self.progress,
            queue_position=queue_position,
            error=self.error,
            created_at=self.created_at,
            warnings=self.warnings,
        )


class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.queue: list[str] = []
        self.executor: Optional[ThreadPoolExecutor] = None
        self.lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._dispatch_task: Optional[asyncio.Task] = None

    def start(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        need_start = False
        if self._dispatch_task is None or self._dispatch_task.done():
            need_start = True
        elif loop is not None:
            try:
                if self._dispatch_task.get_loop() is not loop:
                    need_start = True
            except Exception:
                need_start = True

        if need_start:
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=settings.MAX_CONCURRENT_JOBS)
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    def ensure_started(self):
        self.start()

    def shutdown(self):
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._dispatch_task:
            self._dispatch_task.cancel()
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)

    async def _cleanup_loop(self):
        while True:
            try:
                await asyncio.sleep(60)
                now = time.time()
                async with self.lock:
                    expired = [
                        jid for jid, job in self.jobs.items()
                        if job.status in ("done", "error") and (now - job.updated_at > settings.JOB_TTL_S)
                    ]
                    for jid in expired:
                        del self.jobs[jid]
                        if jid in self.queue:
                            self.queue.remove(jid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _dispatch_loop(self):
        """Dispatches queued jobs as workers become available."""
        from app.pipeline import run_pipeline_task

        while True:
            try:
                await asyncio.sleep(0.5)
                async with self.lock:
                    running_count = sum(1 for j in self.jobs.values() if j.status == "running")
                    if running_count < settings.MAX_CONCURRENT_JOBS and self.queue:
                        next_job_id = self.queue.pop(0)
                        job = self.jobs.get(next_job_id)
                        if job and job.status == "queued":
                            job.status = "running"
                            job.stage = "load"
                            job.updated_at = time.time()
                            loop = asyncio.get_running_loop()

                            def make_progress_cb(target_job: Job):
                                def cb(stage_name: str, prog_val: float):
                                    target_job.stage = stage_name
                                    target_job.progress = prog_val
                                    target_job.updated_at = time.time()
                                return cb

                            # Run worker in ThreadPoolExecutor with progress callback
                            future = loop.run_in_executor(
                                self.executor,
                                run_pipeline_task,
                                job.id,
                                job.image_bytes,
                                job.params.model_dump(),
                                make_progress_cb(job),
                            )
                            asyncio.create_task(self._monitor_job(job, future))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in dispatch loop: {e}")

    async def _monitor_job(self, job: Job, future: asyncio.Future):
        try:
            result = await asyncio.wait_for(future, timeout=settings.JOB_TIMEOUT_S)
            async with self.lock:
                job.status = "done"
                job.stage = "done"
                job.progress = 1.0
                job.svg_data = result["svg_bytes"]
                job.png_data = result.get("png_bytes")
                job.report_data = result.get("report")
                job.warnings = result.get("report", {}).get("warnings", [])
                job.updated_at = time.time()
                # Clear raw input image from memory
                job.image_bytes = b""
        except asyncio.TimeoutError:
            async with self.lock:
                job.status = "error"
                job.stage = "timeout"
                job.error = f"Job timed out after {settings.JOB_TIMEOUT_S} seconds"
                job.updated_at = time.time()
                job.image_bytes = b""
        except Exception as e:
            async with self.lock:
                job.status = "error"
                job.stage = "error"
                job.error = str(e)
                job.updated_at = time.time()
                job.image_bytes = b""

    async def add_job(self, params: PipelineParams, image_bytes: bytes) -> str:
        self.ensure_started()
        async with self.lock:
            if len(self.queue) >= settings.QUEUE_LENGTH_CAP:
                raise ValueError("Queue is full (429)")

            job_id = str(uuid.uuid4())
            job = Job(job_id=job_id, params=params, image_bytes=image_bytes)
            self.jobs[job_id] = job
            self.queue.append(job_id)
            return job_id

    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        async with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            queue_pos = self.queue.index(job_id) + 1 if job_id in self.queue else 0
            return job.to_response(queue_position=queue_pos)

    async def delete_job(self, job_id: str) -> bool:
        async with self.lock:
            if job_id in self.jobs:
                if job_id in self.queue:
                    self.queue.remove(job_id)
                del self.jobs[job_id]
                return True
            return False


job_manager = JobManager()
