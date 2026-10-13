import io
import json
import time
import zipfile
import cv2
import numpy as np
import httpx
from PIL import Image

from app.config import SARVAM_API_KEY, SARVAM_API_URL, OCR_CONFIDENCE_THRESHOLD


def _parse_sarvam_json_blocks(jdata) -> str:
    """Extract text strings from Sarvam AI JSON output blocks or dict structure."""
    lines = []
    if isinstance(jdata, dict):
        if "blocks" in jdata and isinstance(jdata["blocks"], list):
            for block in jdata["blocks"]:
                if isinstance(block, dict) and "text" in block:
                    t = str(block["text"]).strip()
                    if t:
                        lines.append(t)
        elif "text" in jdata:
            lines.append(str(jdata["text"]).strip())
        elif "extracted_text" in jdata:
            lines.append(str(jdata["extracted_text"]).strip())
        elif "document" in jdata and isinstance(jdata["document"], str):
            lines.append(jdata["document"].strip())
            
        for k, v in jdata.items():
            if k not in ["blocks", "text", "extracted_text", "document"]:
                sub = _parse_sarvam_json_blocks(v)
                if sub:
                    lines.append(sub)
    elif isinstance(jdata, list):
        for item in jdata:
            sub = _parse_sarvam_json_blocks(item)
            if sub:
                lines.append(sub)
    return "\n".join([l for l in lines if l.strip()])


def _extract_text_from_zip(content_bytes: bytes) -> str:
    """Extract text from Sarvam AI response zip archive or raw text bytes."""
    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
            extracted_parts = []
            for fname in z.namelist():
                if fname.endswith((".md", ".txt", ".json", ".html")) or "." not in fname:
                    raw_text = z.read(fname).decode("utf-8", errors="ignore").strip()
                    if not raw_text:
                        continue
                    if fname.endswith(".json"):
                        try:
                            jdata = json.loads(raw_text)
                            parsed_txt = _parse_sarvam_json_blocks(jdata)
                            extracted_parts.append(parsed_txt if parsed_txt else raw_text)
                        except Exception:
                            extracted_parts.append(raw_text)
                    else:
                        extracted_parts.append(raw_text)
            return "\n".join([p for p in extracted_parts if p.strip()])
    except Exception:
        text = content_bytes.decode("utf-8", errors="ignore").strip()
        if text.startswith("{") or text.startswith("["):
            try:
                jdata = json.loads(text)
                parsed = _parse_sarvam_json_blocks(jdata)
                if parsed:
                    return parsed
            except Exception:
                pass
        return text


def preprocess_image(image_bytes: bytes) -> bytes:
    """
    Preprocess and optimize image bytes for Sarvam AI OCR upload.
    Converts image to JPEG and downscales extremely large photos (>2400px).
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return image_bytes

        height, width = img.shape[:2]
        max_dim = 2400

        if max(height, width) > max_dim:
            scale = max_dim / float(max(height, width))
            new_w = int(width * scale)
            new_h = int(height * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Always encode to JPEG to match the API payload MIME expectations
        is_success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if is_success:
            return buffer.tobytes()

        return image_bytes
    except Exception:
        return image_bytes


def extract(image_bytes: bytes) -> dict:
    """
    Extract text from a nutrition label image using Sarvam AI OCR API.
    Returns structured text lines, combined full text, and detection metadata.
    """
    api_key = SARVAM_API_KEY.strip()
    if not api_key or api_key == "your_sarvam_api_key_here":
        raise ValueError(
            "SARVAM_API_KEY is not configured. Please set SARVAM_API_KEY in backend/.env "
            "or environment variables to enable Sarvam AI OCR."
        )

    # Preprocess image bytes
    optimized_bytes = preprocess_image(image_bytes)

    text_content = ""
    lines_output = []

    # Method 1: Try using official sarvamai SDK if installed
    sdk_success = False
    try:
        from sarvamai import SarvamAI
        client = SarvamAI(api_subscription_key=api_key)
        
        file_obj = io.BytesIO(optimized_bytes)
        file_obj.name = "label_photo.jpg"
        
        job = client.doc_ai.digitise(file=file_obj, output_format="md")
        
        if hasattr(job, "job_id"):
            job_id = job.job_id
            max_attempts = 15
            for _ in range(max_attempts):
                status_res = client.doc_ai.get_status(job_id=job_id)
                status_str = getattr(status_res, "status", "").lower()
                if status_str == "completed":
                    download_info = client.doc_ai.get_download_url(job_id=job_id)
                    download_url = getattr(download_info, "url", None)
                    if download_url:
                        with httpx.Client(timeout=15.0) as http_client:
                            r = http_client.get(download_url)
                            if r.status_code == 200:
                                text_content = _extract_text_from_zip(r.content)
                                sdk_success = True
                    break
                elif status_str in ["failed", "rejected"]:
                    break
                time.sleep(1.5)
    except Exception:
        sdk_success = False

    # Method 2: Direct REST API polling with fallback formats (md -> json)
    if not sdk_success or not text_content:
        base_url = SARVAM_API_URL.rstrip("/")
        headers = {"api-subscription-key": api_key}

        with httpx.Client(timeout=40.0) as client:
            for fmt in ["md", "json"]:
                if text_content and text_content.strip():
                    break
                files = {"file": ("label_photo.jpg", optimized_bytes, "image/jpeg")}
                resp = client.post(
                    f"{base_url}/doc-ai/v1/job/digitise",
                    headers=headers,
                    files=files,
                    data={"output_format": fmt}
                )

                if resp.status_code in (200, 201):
                    data = resp.json()
                    job_id = data.get("job_id")
                    if job_id:
                        for _ in range(20):
                            time.sleep(1.5)
                            status_resp = client.get(f"{base_url}/doc-ai/v1/job/{job_id}/status", headers=headers)
                            if status_resp.status_code in (200, 201):
                                s_data = status_resp.json()
                                st = str(s_data.get("status", "")).lower()

                                if st == "completed":
                                    # Fetch results directly from the new /results endpoint
                                    results_resp = client.get(f"{base_url}/doc-ai/v1/job/{job_id}/results", headers=headers)
                                    if results_resp.status_code == 200:
                                        parsed = _parse_sarvam_json_blocks(results_resp.json())
                                        if parsed and parsed.strip():
                                            text_content = parsed
                                            
                                    # Legacy fallback: check for download_url
                                    if not text_content or not text_content.strip():
                                        succ_files = s_data.get("successful_files", [])
                                        for file_info in succ_files:
                                            dl_url = file_info.get("download_url")
                                            if dl_url:
                                                dl_res = client.get(dl_url)
                                                if dl_res.status_code == 200:
                                                    extracted = _extract_text_from_zip(dl_res.content)
                                                    if extracted and extracted.strip():
                                                        text_content = extracted
                                                        break
                                    break
                                elif st in ["failed", "rejected"]:
                                    break

    if not text_content or not text_content.strip():
        raise ValueError(
            "Sarvam AI OCR could not detect readable text from this label photo. "
            "Please ensure the image is clear, well-lit, upright, and closely focuses on the nutrition facts or ingredients table."
        )

    # Clean and split into lines
    raw_lines = [line.strip() for line in text_content.splitlines() if line.strip()]

    for line in raw_lines:
        lines_output.append({
            "text": line,
            "confidence": 0.99
        })

    combined_text = "\n".join(raw_lines)

    return {
        "lines": lines_output,
        "combined_text": combined_text,
        "total_detections": len(lines_output),
        "filtered_detections": len(lines_output),
        "engine": "Sarvam AI OCR",
    }


