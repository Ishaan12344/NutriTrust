"""
API Routes — Scan & Rate endpoints
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

from app.services import barcode_service, ocr_service, parser_service, scoring_service

router = APIRouter(prefix="/api", tags=["scan"])


# ─────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────

class BarcodeRequest(BaseModel):
    barcode: str = Field(..., description="Product barcode (EAN-13, UPC-A, etc.)")


class ManualNutritionRequest(BaseModel):
    """For direct nutrition input (testing & future company portal)."""
    product_name: str = Field(default="Manual Entry", description="Product name")
    energy_kcal: float = Field(default=0, ge=0, description="Energy in kcal per 100g")
    total_fat: float = Field(default=0, ge=0, description="Total fat in g per 100g")
    saturated_fat: float = Field(default=0, ge=0, description="Saturated fat in g per 100g")
    trans_fat: float = Field(default=0, ge=0, description="Trans fat in g per 100g")
    sugar: float = Field(default=0, ge=0, description="Sugar in g per 100g")
    sodium: float = Field(default=0, ge=0, description="Sodium in mg per 100g")
    fiber: float = Field(default=0, ge=0, description="Fiber in g per 100g")
    protein: float = Field(default=0, ge=0, description="Protein in g per 100g")
    ingredients_text: str = Field(default="", description="Ingredients list text")


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/scan/barcode")
async def scan_barcode(request: BarcodeRequest):
    """
    Scan a product by barcode.
    Looks up Open Food Facts API → scores the product.
    """
    barcode = request.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="Barcode cannot be empty")

    # Look up product
    product_data = await barcode_service.lookup(barcode)
    if product_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product with barcode '{barcode}' not found in Open Food Facts. "
                   f"Try uploading a label image instead.",
        )

    # Score the product
    result = scoring_service.rate(product_data)
    return result


@router.post("/scan/image")
async def scan_image(
    nutrition_image: UploadFile | None = File(None),
    ingredients_image: UploadFile | None = File(None),
    image: UploadFile | None = File(None),
):
    """
    Scan up to 2 label images:
    - nutrition_image: Photo of the Nutrition Facts Table
    - ingredients_image: Photo of the Ingredients List
    Allows 1 or both images.
    """
    # Legacy single 'image' parameter fallback
    if not nutrition_image and not ingredients_image and image:
        nutrition_image = image

    if not nutrition_image and not ingredients_image:
        raise HTTPException(
            status_code=400,
            detail="Please upload at least 1 image (Nutrition Facts photo or Ingredients list photo).",
        )

    allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp", "image/bmp"]

    ocr_nutrition = None
    ocr_ingredients = None

    try:
        # 1. Process Nutrition Image if provided
        if nutrition_image and nutrition_image.filename:
            if nutrition_image.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type for Nutrition image: {nutrition_image.content_type}.",
                )
            bytes_nutr = await nutrition_image.read()
            if len(bytes_nutr) > 0:
                if len(bytes_nutr) > 10 * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="Nutrition image too large (max 10MB)")
                ocr_nutrition = ocr_service.extract(bytes_nutr)

        # 2. Process Ingredients Image if provided
        if ingredients_image and ingredients_image.filename:
            if ingredients_image.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type for Ingredients image: {ingredients_image.content_type}.",
                )
            bytes_ingr = await ingredients_image.read()
            if len(bytes_ingr) > 0:
                if len(bytes_ingr) > 10 * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="Ingredients image too large (max 10MB)")
                ocr_ingredients = ocr_service.extract(bytes_ingr)

        if not ocr_nutrition and not ocr_ingredients:
            raise HTTPException(
                status_code=400,
                detail="Please upload a valid Nutrition Facts or Ingredients list photo.",
            )

        # Parse OCR text into structured data (dual or single)
        product_data = parser_service.parse_dual(ocr_nutrition, ocr_ingredients)

        # Score the product
        result = scoring_service.rate(product_data)

        # Include OCR metadata in response
        ocr_meta = {}
        if ocr_nutrition:
            ocr_meta["nutrition_ocr"] = {
                "engine": ocr_nutrition.get("engine", "Sarvam AI OCR"),
                "detections": ocr_nutrition.get("total_detections", 0),
            }
        if ocr_ingredients:
            ocr_meta["ingredients_ocr"] = {
                "engine": ocr_ingredients.get("engine", "Sarvam AI OCR"),
                "detections": ocr_ingredients.get("total_detections", 0),
            }
        result["ocr_metadata"] = ocr_meta

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing label image(s): {str(e)}",
        )


@router.post("/rate")
async def rate_manual(request: ManualNutritionRequest):
    """
    Rate a product from manually entered nutrition data.
    Useful for testing and future company certification portal.
    """
    product_data = {
        "product": {
            "name": request.product_name,
            "brand": "Manual Entry",
            "barcode": None,
            "categories": "",
            "image_url": "",
            "source": "manual",
        },
        "nutrition_per_100g": {
            "energy_kcal": request.energy_kcal,
            "total_fat": request.total_fat,
            "saturated_fat": request.saturated_fat,
            "trans_fat": request.trans_fat,
            "sugar": request.sugar,
            "sodium": request.sodium,
            "fiber": request.fiber,
            "protein": request.protein,
        },
        "ingredients_text": request.ingredients_text,
        "additives_tags": [],
        "nova_group": None,
    }

    result = scoring_service.rate(product_data)
    return result
