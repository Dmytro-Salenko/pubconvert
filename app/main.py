"""PubConvert — convert Microsoft Publisher files to PDF, DOCX, SVG."""

import asyncio
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from app.converter import ConversionError, convert

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
CONVERSION_TIMEOUT = int(os.getenv("CONVERSION_TIMEOUT", "120"))
COFFEE_URL = os.getenv("COFFEE_URL", "")
TMP_DIR = Path(os.getenv("TMP_DIR", "/tmp/pubconvert"))
CLEANUP_AFTER_MINUTES = 10

# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------


def _cleanup_old_jobs() -> None:
    """Remove job directories older than CLEANUP_AFTER_MINUTES."""
    if not TMP_DIR.exists():
        return
    cutoff = time.time() - CLEANUP_AFTER_MINUTES * 60
    for entry in TMP_DIR.iterdir():
        if entry.is_dir():
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                pass


async def _periodic_cleanup() -> None:
    """Background loop: clean up expired jobs every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        _cleanup_old_jobs()


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_old_jobs()
    task = asyncio.create_task(_periodic_cleanup())
    yield
    # Shutdown
    task.cancel()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="PubConvert", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    """Health check."""
    return {"status": "ok"}


@app.get("/api/config")
def get_config():
    """Return public configuration for the frontend."""
    return {
        "max_upload_mb": MAX_UPLOAD_MB,
        "coffee_url": COFFEE_URL,
    }


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the single-page frontend."""
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/convert")
async def convert_file(
    file: UploadFile = File(...),
    format: str = Form(...),
):
    """Upload a .pub file and convert it to the requested format.

    Returns a JSON object with download_url and filename.
    """
    # --- Validate format ---
    allowed_formats = ("pdf", "docx", "svg")
    if format not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Choose one of: {', '.join(allowed_formats)}",
        )

    # --- Validate file extension ---
    if not file.filename or not file.filename.lower().endswith(".pub"):
        raise HTTPException(
            status_code=400,
            detail="Only .pub files are accepted.",
        )

    # --- Read and validate file size ---
    content = await file.read()
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large. Maximum size is {MAX_UPLOAD_MB} MB.",
        )

    if len(content) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    # --- Create job directory ---
    job_id = str(uuid.uuid4())
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True)

    # Save with a fixed internal name to avoid path issues
    input_path = job_dir / "input.pub"
    input_path.write_bytes(content)

    # --- Convert ---
    try:
        output_filename = convert(
            input_path=input_path,
            output_dir=job_dir,
            fmt=format,
            timeout=CONVERSION_TIMEOUT,
        )
    except ConversionError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail="Conversion failed unexpectedly. Please try again.",
        )

    # --- Build user-friendly download name ---
    original_stem = Path(file.filename).stem
    download_name = f"{original_stem}.{format}"

    return {
        "download_url": f"/api/files/{job_id}/{output_filename}",
        "filename": download_name,
        "format": format,
    }


@app.get("/api/files/{job_id}/{filename}")
def download_file(job_id: str, filename: str):
    """Download a converted file by job ID."""
    # Validate job_id is a UUID (prevents path traversal)
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID.")

    # Reject any path traversal attempts in filename
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    file_path = TMP_DIR / job_id / filename
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File not found. It may have been automatically deleted after 10 minutes.",
        )

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )
