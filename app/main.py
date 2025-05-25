# file: main.py

'''
Main.py initializes the FastAPI application for the Medical OCR Extractor system.
It defines the API endpoints, middleware, exception handlers, and mounts static frontend assets.
The core functionality includes PDF upload handling, OCR extraction using Azure, and returning structured JSON.
'''

from fastapi import Depends, FastAPI, File, UploadFile, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from datetime import datetime
from typing import List
import logging
from app.services.ocr_service import OCRService
from app.models import APIResponse, HealthCheckResponse, ErrorResponse, ValidationErrorResponse, ExtractionResult

# Setup logging to capture application-level logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OCRService instance placeholder (initialized lazily)
ocr_service: OCRService = None

# FastAPI app instance with metadata
app = FastAPI(
    title="Medical OCR Extractor",
    description="Upload PDF medical reports and extract structured health data using Azure OCR.",
    version="1.0.0"
)

# Configure CORS middleware to allow requests from any origin (can be restricted for production use)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the static files directory (for serving frontend)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Dependency injection for OCRService instance (lazy initialization)
async def get_ocr_service() -> OCRService:
    """Dependency to get OCR service instance"""
    global ocr_service
    if ocr_service is None:
        ocr_service = OCRService()  # Initialize only when needed
    return ocr_service

# Custom exception handler for HTTP exceptions
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.error(f"HTTP Exception: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": "HTTP error",
            "error": str(exc.detail),
            "timestamp": datetime.utcnow().isoformat(),
            "data": None
        }
    )

# Custom exception handler for request validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ValidationErrorResponse(errors=exc.errors()).model_dump()
    )

# Fallback handler for uncaught exceptions
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            message="Unexpected server error",
            error=str(exc)
        ).model_dump()
    )

# Route to serve the frontend upload page
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """
    Serves the static index.html page with upload form.
    """
    try:
        with open("app/static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="index.html not found")

# Route to handle PDF uploads and trigger OCR extraction
@app.post("/upload")
async def upload_pdfs(files: List[UploadFile] = File(...), service: OCRService = Depends(get_ocr_service)):
    if not files:
        raise HTTPException(status_code=400, detail="No PDF files uploaded")

    file = files[0]  # For now, only handle the first file in the list
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"{file.filename} is not a PDF")

    try:
        pdf_bytes = await file.read()  # Read PDF file content
        extraction_result = await service.extract_text_from_pdf(pdf_bytes)  # Run OCR and extraction

        # Return structured JSON response with patient info and test results
        return {
            "success": True,
            "message": "PDF processed successfully",
            "error": None,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "patient": extraction_result.patient_information.model_dump(),
                "investigations": [inv.model_dump() for inv in extraction_result.investigations]
            }
        }

    except HTTPException:
        raise  # Let FastAPI handle HTTPExceptions explicitly raised
    except Exception as e:
        logger.exception(f"Error processing file: {file.filename}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Failed to process...",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "data": None
            }
        )

# Health check route to confirm app is running
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Basic health check route.
    """
    return HealthCheckResponse()
