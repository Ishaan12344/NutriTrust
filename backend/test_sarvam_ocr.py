import io
import unittest

from PIL import Image

from sarvam_ocr import _parse_json_text, _prepare_image


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

    def test_json_blocks_are_flattened_to_text(self):
        text = _parse_json_text(
            '{"blocks": [{"text": "Ingredients: oats"}, {"text": "Protein 4 g"}]}'
        )
        self.assertEqual(text, "Ingredients: oats\nProtein 4 g")


if __name__ == "__main__":
    unittest.main()
