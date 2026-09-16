import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app import ocr
from app.models import Application, VerifyResponse
from app.verify import verify

MAX_IMAGES = 6
MAX_IMAGE_BYTES = 20 * 1024 * 1024
QUEUE_TIMEOUT_SECONDS = 30

# OCR already uses every core for a single label, so running several at once only makes
# each one slower. Requests beyond this wait their turn.
ocr_slots = asyncio.Semaphore(int(os.environ.get("OCR_CONCURRENCY", "1")))


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(ocr.warm_up)
    yield


app = FastAPI(title="Label Check", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/verify")
async def verify_label(
    images: Annotated[list[UploadFile], File()],
    application: Annotated[str, Form()],
) -> VerifyResponse:
    try:
        details = Application.model_validate_json(application)
    except ValidationError as exc:
        raise HTTPException(422, "The application details could not be read.") from exc

    if len(images) > MAX_IMAGES:
        raise HTTPException(400, f"Add no more than {MAX_IMAGES} images for one label.")

    decoded = []
    for upload in images:
        data = await upload.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, f"{upload.filename} is larger than 20 MB.")
        try:
            decoded.append(await run_in_threadpool(ocr.load_image, data))
        except ocr.ImageError as exc:
            raise HTTPException(
                415, f"{upload.filename} could not be opened. Use a JPG, PNG or WEBP image."
            ) from exc

    try:
        await asyncio.wait_for(ocr_slots.acquire(), QUEUE_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise HTTPException(
            503, "The checker is busy. Try again in a moment.", headers={"Retry-After": "5"}
        ) from exc
    try:
        return await run_in_threadpool(verify, decoded, details)
    finally:
        ocr_slots.release()


# The Docker image copies the built frontend here. In local dev, Vite serves it instead.
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
