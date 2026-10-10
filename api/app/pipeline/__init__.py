import logging
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger(__name__)


def run_pipeline_task(job_id: str, image_bytes: bytes, params_dict: dict) -> dict:
    """Entry point for running the vectorizer pipeline in a worker process."""
    from app.pipeline.runner import run_pipeline

    return run_pipeline(job_id, image_bytes, params_dict)
