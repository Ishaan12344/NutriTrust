import io
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from PIL import Image

from sarvam_ocr import _parse_json_text, _prepare_image, _with_retry, extract_text_from_image


class SarvamOcrHelpersTests(unittest.TestCase):
    def test_large_image_is_uprighted_and_downscaled_to_jpeg(self):
        source = io.BytesIO()
        Image.new("RGB", (3000, 1000), (200, 30, 30)).save(source, format="PNG")

        prepared, name, content_type = _prepare_image(
            source.getvalue(), "label.png", "image/png"
        )

        self.assertEqual(name, "label.jpg")
        self.assertEqual(content_type, "image/jpeg")
        with Image.open(io.BytesIO(prepared)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(max(image.size), 2400)

    def test_transient_network_failure_is_retried_with_backoff(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise requests.RequestException("transient")
            return "ok"

        with patch("sarvam_ocr.time.sleep") as sleep:
            result = _with_retry(flaky)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1.0])

    def test_json_blocks_are_flattened_to_text(self):
        text = _parse_json_text(
            '{"blocks": [{"text": "Ingredients: oats"}, {"text": "Protein 4 g"}]}'
        )
        self.assertEqual(text, "Ingredients: oats\nProtein 4 g")

    def test_extract_uses_parse_job_and_download_headers(self):
        source = io.BytesIO()
        Image.new("RGB", (20, 20), (200, 30, 30)).save(source, format="PNG")

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("document.md", "Ingredients: oats")

        doc_ai = SimpleNamespace(
            digitise=Mock(return_value=SimpleNamespace(job_id="job-123")),
            get_status=Mock(return_value=SimpleNamespace(status="completed")),
            get_download_url=Mock(
                return_value=SimpleNamespace(
                    method="GET",
                    url="https://example.test/ocr.zip",
                    headers={"x-download-token": "token"},
                )
            ),
        )
        response = Mock()
        response.content = archive.getvalue()

        with (
            patch(
                "sarvam_ocr._get_client",
                return_value=SimpleNamespace(doc_ai=doc_ai),
            ),
            patch(
                "sarvam_ocr.get_settings",
                return_value=SimpleNamespace(
                    sarvam_timeout_seconds=10,
                    sarvam_download_timeout_seconds=10,
                ),
            ),
            patch("sarvam_ocr.requests.request", return_value=response) as request,
        ):
            result = extract_text_from_image(
                source.getvalue(), "label.png", "image/png"
            )

        self.assertEqual(result["text"], "Ingredients: oats")
        doc_ai.digitise.assert_called_once()
        self.assertEqual(doc_ai.digitise.call_args.kwargs["language"], "en-IN")
        request.assert_called_once_with(
            method="GET",
            url="https://example.test/ocr.zip",
            headers={"x-download-token": "token"},
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
