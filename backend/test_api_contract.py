"""Small integration tests for public routes that Flutter relies on."""

import asyncio
import unittest

import httpx

from main import app


class ApiContractTests(unittest.TestCase):
    @staticmethod
    def request(method: str, path: str, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def test_service_and_health_routes_are_available(self):
        root = self.request("GET", "/")
        health = self.request("GET", "/health")
        self.assertEqual(root.status_code, 200)
        self.assertEqual(root.json(), {"message": "NutriTrust backend is running", "docs": "/docs"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})

    def test_openapi_documents_flutter_routes(self):
        response = self.request("GET", "/openapi.json")
        self.assertEqual(response.status_code, 200)
        spec = response.json()
        paths = spec["paths"]
        self.assertIn("/api/v1/ocr", paths)
        self.assertIn("/api/v1/manual-assessment", paths)
        self.assertIn("/api/v1/open-food-facts/{barcode}", paths)
        self.assertIn("/api/v1/summary", paths)
        self.assertIn("/api/v1/auth/register", paths)
        self.assertIn("/api/v1/auth/login", paths)
        self.assertIn("/api/v1/user/profile", paths)
        ocr_schema = paths["/api/v1/ocr"]["post"]["requestBody"]["content"][
            "multipart/form-data"
        ]["schema"]
        schema_name = ocr_schema["$ref"].rsplit("/", 1)[-1]
        self.assertIn(
            "ingredients_file",
            spec["components"]["schemas"][schema_name]["properties"],
        )

    def test_ocr_rejects_unsupported_content_type_before_external_work(self):
        response = self.request(
            "POST",
            "/api/v1/ocr",
            files={"file": ("label.gif", b"image-bytes", "image/gif")},
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["detail"], "Upload a JPG, JPEG or PNG image.")


if __name__ == "__main__":
    unittest.main()
