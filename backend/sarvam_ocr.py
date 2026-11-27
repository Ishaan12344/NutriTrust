
import io
import json
import logging
import time
import zipfile
from functools import lru_cache
from pathlib import PurePosixPath

import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from sarvamai import SarvamAI
from sarvamai.core.api_error import ApiError

from app_config import get_settings

logger = logging.getLogger(__name__)

TERMINAL_STATES = {
    "completed",
    "partially_completed",
    "failed",
    "rejected",
}

SUPPORTED_TYPES = {
    "image/jpeg",
    "image/png",
}

MAX_IMAGE_DIMENSION = 2400
JPEG_QUALITY = 90


@lru_cache
def _get_client() -> SarvamAI:
    """Create the SDK client only when OCR is actually requested.

    This keeps health checks and barcode lookup available when an OCR key has
    not been configured, while still failing the OCR request with an actionable
    error instead of sending an unauthenticated request.
    """
    api_key = get_settings().sarvam_api_key
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is missing. Add it to backend/.env.")
    return SarvamAI(api_subscription_key=api_key)


def _prepare_image(
    image_bytes: bytes,
    filename: str,
    content_type: str,
) -> tuple[bytes, str, str]:
    """Upright and downscale the photo before upload.

    Phone photos are often much larger than OCR needs and may carry EXIF
    orientation metadata that OCR ignores.  Normalising them reduces upload
    time and improves recognition.  Undecodable input is passed through so the
    provider can still make the final call.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            image.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS
            )
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Could not preprocess image for OCR (%s); sending original.", exc)
        return image_bytes, filename, content_type

    prepared = output.getvalue()
    logger.info(
        "prepared OCR image: %s bytes -> %s bytes", len(image_bytes), len(prepared)
    )
    return prepared, f"{PurePosixPath(filename).stem or 'food-label'}.jpg", "image/jpeg"


def _parse_json_text(raw: str) -> str:
    """Extract text blocks from Sarvam's JSON parse output."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip()

    lines: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key in ("text", "extracted_text", "document"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    lines.append(value.strip())
                    return
            for key in ("blocks", "pages", "children", "data", "result"):
                if key in node:
                    walk(node[key])
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str) and node.strip():
            lines.append(node.strip())

    walk(data)
    return "\n".join(dict.fromkeys(line for line in lines if line))


def extract_text_from_image(
    image_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict:
    logger.info("starting Sarvam OCR: filename=%s type=%s bytes=%s", filename, content_type, len(image_bytes))
    if content_type not in SUPPORTED_TYPES:
        raise ValueError("Only JPG, JPEG and PNG images are supported.")

    if not image_bytes:
        raise ValueError("The uploaded image is empty.")

    prepared_bytes, prepared_name, prepared_type = _prepare_image(
        image_bytes, filename, content_type
    )

    client = _get_client()
    timeout_seconds = get_settings().sarvam_timeout_seconds
    download_timeout_seconds = get_settings().sarvam_download_timeout_seconds

    # Sarvam's SDK accepts a list of file tuples.
    try:
        job = client.doc_ai.parse(
            file=[
                (
                    prepared_name,
                    io.BytesIO(prepared_bytes),
                    prepared_type,
                )
            ],
            language="en-IN",
        )
    except ApiError as exc:
        raise RuntimeError(
            f"Sarvam rejected the OCR request (HTTP {exc.status_code})."
        ) from exc


    logger.info("Sarvam OCR job created: job_id=%s", job.job_id)

    deadline = time.monotonic() + timeout_seconds

    try:
        while True:
            status = client.doc_ai.get_status(job_id=job.job_id)
            state = status.status.lower()
            logger.info("Sarvam OCR poll: job_id=%s status=%s", job.job_id, state)

            if state in TERMINAL_STATES:
                break

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "OCR is taking too long. Please try again."
                )

            time.sleep(3)

        if state not in {"completed", "partially_completed"}:
            raise RuntimeError(
                f"Sarvam OCR job ended with status: {state}."
            )

        download = client.doc_ai.get_download_url(
            job_id=job.job_id
        )
        logger.info("Sarvam OCR completed; downloading output: job_id=%s", job.job_id)

        response = requests.request(
            method=download.method,
            url=download.url,
            headers=download.headers,
            timeout=download_timeout_seconds,
        )
        response.raise_for_status()

    except ApiError as exc:
        raise RuntimeError(
            f"Sarvam OCR processing failed (HTTP {exc.status_code})."
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(
            "Could not download the OCR output from Sarvam."
        ) from exc

    # Parse output is a ZIP containing the document text and per-page metadata.
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            candidates = [
                name for name in archive.namelist()
                if not name.endswith("/")
                and PurePosixPath(name).suffix.lower()
                in {".md", ".html", ".txt", ".json"}
                and "metadata/" not in name.lower()
            ]

            if not candidates:
                raise RuntimeError(
                    "Sarvam completed OCR but returned no text file."
                )

            # Prefer the primary Markdown document, then HTML, text, and JSON.
            preference = {".md": 0, ".html": 1, ".txt": 2, ".json": 3}
            candidates.sort(
                key=lambda name: (
                    preference.get(PurePosixPath(name).suffix.lower(), 4),
                    name,
                )
            )

            raw_text = archive.read(candidates[0]).decode(
                "utf-8-sig", errors="replace"
            )
            extracted_text = (
                _parse_json_text(raw_text)
                if PurePosixPath(candidates[0]).suffix.lower() == ".json"
                else raw_text.strip()
            )

    except zipfile.BadZipFile as exc:
        raise RuntimeError(
            "Sarvam returned an invalid OCR output archive."
        ) from exc

    if not extracted_text:
        raise RuntimeError(
            "No readable text was detected. Try a clearer image."
        )

    return {
        "job_id": job.job_id,
        "status": state,
        "text": extracted_text,
    }
