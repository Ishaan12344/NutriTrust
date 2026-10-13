"""
NutriTrust Backend — Main FastAPI Application
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from app.routes import scan

app = FastAPI(
    title="NutriTrust — AI-Powered Food Intelligence Platform",
    description="Backend API for barcode scanning, nutrition label OCR, and hybrid food rating.",
    version="1.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(scan.router)

# Static files path
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", tags=["frontend"])
async def serve_frontend():
    """Serve interactive Web UI."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "status": "online",
        "service": "NutriTrust API Engine",
        "docs_url": "/docs",
    }


@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "healthy"}

