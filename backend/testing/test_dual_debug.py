import sys
sys.path.insert(0, r'D:\Projects\NutriTrust\backend')

import asyncio
from unittest.mock import AsyncMock, patch
from main import app

LABEL_TEXT = (
    "Product Name: Sample Bar\n"
    "Ingredients: oats, sugar, cocoa\n"
    "Contains: milk\n"
    "Nutrition information per 100 g\n"
    "Total Fat | 5 g\nProtein | 4 g"
)


async def test_dual():
    async def request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"file": ("label.png", b"image-bytes", "image/png")}
            files["ingredients_file"] = (
                "ingredients.png", b"ingredients-bytes", "image/png",
            )
            return await client.post("/api/v1/ocr", files=files)

    def fake_ocr(_image_bytes, filename, _content_type):
        if filename == "ingredients.png":
            return {
                "job_id": "ocr-job-2", "status": "completed", "text": "Ingredients: oats, sugar, cocoa, raising agent (500)\nContains: milk\nMay contain traces of soy",
            }
        return {
            "job_id": "ocr-job-1", "status": "completed", "text": LABEL_TEXT,
        }

    with patch("main.extract_text_from_image", side_effect=fake_ocr), patch("main.fetch_open_food_facts_product", new=AsyncMock()) as fetch:
        response = asyncio.run(request())

    print(f"Status: {response.status_code}")
    body = response.json()
    print(f"\nFull response keys: {list(body.keys())}")
    print(f"\nproduct_analysis: {body.get('product_analysis', {})}")
    print(f"\nclassification: {body.get('product_analysis', {}).get('classification', {})}")
    print(f"\nadditives_tags: {body.get('product_analysis', {}).get('classification', {}).get('additives_tags', 'N/A')}")
    print(f"\nadditive_regulatory: {body.get('additive_regulatory', 'N/A')}")
    print(f"\nnutri_score: {body.get('nutri_score', 'N/A')}")
    print(f"\nova: {body.get('nova', 'N/A')}")
    print(f"\nscoring: {body.get('scoring', 'N/A')}")


asyncio.run(test_dual())