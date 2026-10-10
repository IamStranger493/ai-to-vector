import os
import sys
import io
import time
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api")))

from app.main import app
from app.config import settings
from app.jobs import job_manager


def make_dummy_png(w=64, h=64):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (100, 150, 200)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_auth_enforcement():
    # Set API_KEY in settings to test 401
    orig_key = settings.API_KEY
    settings.API_KEY = "test-secret-key-123"
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Missing header -> 401
            resp = await client.post("/jobs", files={"file": ("test.png", make_dummy_png(), "image/png")})
            assert resp.status_code == 401

            # 2. Wrong key -> 401
            resp = await client.post(
                "/jobs",
                files={"file": ("test.png", make_dummy_png(), "image/png")},
                headers={"X-API-Key": "wrong-key"},
            )
            assert resp.status_code == 401

            # 3. Correct key -> 202
            resp = await client.post(
                "/jobs",
                files={"file": ("test.png", make_dummy_png(), "image/png")},
                headers={"X-API-Key": "test-secret-key-123"},
            )
            assert resp.status_code == 202
            assert "job_id" in resp.json()
    finally:
        settings.API_KEY = orig_key


@pytest.mark.asyncio
async def test_error_status_codes():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 415 Unsupported Media Type (text file disguised as image)
        resp = await client.post(
            "/jobs",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
        assert resp.status_code == 415

        # 422 Bad Params (invalid json or unknown fields due to extra='forbid')
        resp = await client.post(
            "/jobs",
            files={"file": ("test.png", make_dummy_png(), "image/png")},
            data={"params": '{"unknown_field": 123}'},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_job_lifecycle_and_delete():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create job
        resp = await client.post(
            "/jobs",
            files={"file": ("test.png", make_dummy_png(32, 32), "image/png")},
            data={"params": '{"curves": {"mode": "polygon"}}'},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # 2. Poll job status until done
        for _ in range(30):
            status_resp = await client.get(f"/jobs/{job_id}")
            assert status_resp.status_code == 200
            data = status_resp.json()
            if data["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.5)

        assert data["status"] == "done"

        # 3. Verify result endpoints
        svg_resp = await client.get(f"/jobs/{job_id}/svg")
        assert svg_resp.status_code == 200
        assert svg_resp.headers["content-type"].startswith("image/svg+xml")

        png_resp = await client.get(f"/jobs/{job_id}/png")
        assert png_resp.status_code == 200
        assert png_resp.headers["content-type"].startswith("image/png")

        rep_resp = await client.get(f"/jobs/{job_id}/report")
        assert rep_resp.status_code == 200
        assert "metrics" in rep_resp.json()

        # 4. DELETE job
        del_resp = await client.delete(f"/jobs/{job_id}")
        assert del_resp.status_code == 200
        assert del_resp.json() == {"deleted": True}

        # 5. Subsequent get -> 404
        assert (await client.get(f"/jobs/{job_id}")).status_code == 404
