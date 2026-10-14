
import io
import os
import time
import zipfile
from pathlib import PurePosixPath

import requests
from dotenv import load_dotenv
from sarvamai import SarvamAI
from sarvamai.core.api_error import ApiError

load_dotenv()

API_KEY = os.getenv("SARVAM_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "SARVAM_API_KEY is missing. Add it to backend/.env."
    )

client = SarvamAI(api_subscription_key=API_KEY)

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


def extract_text_from_image(
    image_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict:
    if content_type not in SUPPORTED_TYPES:
        raise ValueError("Only JPG, JPEG and PNG images are supported.")

    if not image_bytes:
        raise ValueError("The uploaded image is empty.")

    # Sarvam's SDK accepts a list of file tuples.
    try:
        job = client.doc_ai.digitise(
            file=[
                (
                    filename,
                    io.BytesIO(image_bytes),
                    content_type,
                )
            ],
            language="en-IN",
        )
    except ApiError as exc:
        raise RuntimeError(
            f"Sarvam rejected the OCR request (HTTP {exc.status_code})."
        ) from exc

    deadline = time.monotonic() + 180

    try:
        while True:
            status = client.doc_ai.get_status(job_id=job.job_id)
            state = status.status.lower()

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

        response = requests.request(
            method=download.method,
            url=download.url,
            timeout=60,
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

    # Digitise output is a ZIP containing the document text
    # and per-page metadata.
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            candidates = [
                name for name in archive.namelist()
                if not name.endswith("/")
                and PurePosixPath(name).suffix.lower()
                in {".md", ".html", ".txt"}
                and "metadata/" not in name.lower()
            ]

            if not candidates:
                raise RuntimeError(
                    "Sarvam completed OCR but returned no text file."
                )

            # Prefer the primary Markdown document.
            candidates.sort(
                key=lambda name: (
                    PurePosixPath(name).suffix.lower() != ".md",
                    name,
                )
            )

            extracted_text = archive.read(
                candidates[0]
            ).decode("utf-8-sig", errors="replace").strip()

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
