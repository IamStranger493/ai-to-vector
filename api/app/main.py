import hmac
import io
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from PIL import Image

from app.config import settings
from app.schemas import PipelineParams, JobResponse, JobCreateResponse
from app.jobs import job_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS
    job_manager.start()
    yield
    # Shutdown
    job_manager.shutdown()


app = FastAPI(
    title="Layered Vectorizer API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Check API key if configured in settings."""
    if not settings.API_KEY:
        return  # No key configured in dev/test
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-API-Key header")
    if not hmac.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreateResponse)
async def create_job(
    file: UploadFile = File(...),
    params: Optional[str] = Form(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    verify_api_key(x_api_key)

    # 1. Parse params
    pipeline_params = PipelineParams()
    if params:
        try:
            params_dict = json.loads(params)
            pipeline_params = PipelineParams.model_validate(params_dict)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid params: {e}")

    # 2. Stream and validate file size
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunk_size = 1024 * 64
    content = bytearray()

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Upload exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB",
            )

    image_bytes = bytes(content)

    # 3. Validate image format with Pillow
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            fmt = img.format
            if fmt not in ("PNG", "JPEG", "WEBP"):
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported format: {fmt}. Must be PNG, JPEG, or WEBP.",
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Could not decode image: {e}",
        )

    # 4. Enqueue job
    try:
        job_id = await job_manager.add_job(params=pipeline_params, image_bytes=image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    return JobCreateResponse(job_id=job_id)


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(
    job_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    verify_api_key(x_api_key)
    job_resp = await job_manager.get_job(job_id)
    if not job_resp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job_resp


@app.get("/jobs/{job_id}/svg")
async def get_job_svg(
    job_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    verify_api_key(x_api_key)
    async with job_manager.lock:
        job = job_manager.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.status != "done" or not job.svg_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job result not ready")
        return Response(content=job.svg_data, media_type="image/svg+xml")


@app.get("/jobs/{job_id}/png")
async def get_job_png(
    job_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    verify_api_key(x_api_key)
    async with job_manager.lock:
        job = job_manager.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.status != "done" or not job.png_data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PNG preview not available")
        return Response(content=job.png_data, media_type="image/png")


@app.get("/jobs/{job_id}/report")
async def get_job_report(
    job_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    verify_api_key(x_api_key)
    async with job_manager.lock:
        job = job_manager.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.status != "done" or job.report_data is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Report not ready")
        return JSONResponse(content=job.report_data)


@app.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    verify_api_key(x_api_key)
    deleted = await job_manager.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return {"deleted": True}
