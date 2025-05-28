# file : ocr_service.py

'''
Handles OCR extraction from PDFs using Azure Computer Vision.
This file:
- Uses Azure's Read API to extract text from PDF files.
- Processes the extracted lines to get structured medical data.
- Extracts patient information using regex.
- Applies a template parser and medical keyword matcher.
- Parses tabular lab test results.
- Merges extracted investigations into a final unified list.
'''

import io
import os
import json
import asyncio
import logging
import re
from typing import List, Dict
from app.config import settings
from fastapi import HTTPException
from app.models import APIResponse, ExtractionResult
from app.utils.medical_parser import MedicalTestParser
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials
from app.services.get_test_names import test_name_fields
from app.utils.table_parser import TableLineParser
from app.utils.patient_info import PatientInfoExtractor
from decimal import Decimal, ROUND_HALF_UP
from app.services.get_test_names import test_name_fields


# Set up logging based on environment variable
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self):
        '''Initializes the OCRService with Azure credentials and parsers'''

        # Validate configuration for Azure Vision API
        if not settings.AZURE_VISION_ENDPOINT or not settings.AZURE_VISION_KEY:
            raise ValueError("Azure Vision API credentials not configured")

        # Initialize Azure Computer Vision client
        self.client = ComputerVisionClient(
            settings.AZURE_VISION_ENDPOINT,
            CognitiveServicesCredentials(settings.AZURE_VISION_KEY)
        )

        # Setup retry limits
        self.max_attempts = 30
        self.retry_delay = 1

        # Initialize medical and table parsers
        self.medical_parser = MedicalTestParser()
        self.table_parser = TableLineParser()

    async def extract_text_from_pdf(self, pdf_bytes: bytes) -> ExtractionResult:
        '''Reads a PDF file, sends it to Azure Read API, and polls for the extracted text'''

        # Validate input PDF data
        if not pdf_bytes:
            raise ValueError("No PDF data received")

        try:
            # Convert bytes into stream and initiate OCR read request
            stream = io.BytesIO(pdf_bytes)
            read_response = await asyncio.to_thread(
                self.client.read_in_stream,     # sends the file to Azure's OCR (Optical Character Recognition) service.
                stream,
                raw=True
            )

            # Extract operation ID from Azure response
            operation_location = read_response.headers.get("Operation-Location")
            operation_id = operation_location.split("/")[-1]

            # Poll Azure for OCR result
            return await self.poll_ocr_result(operation_id)

        except Exception as e:
            # Log and raise HTTP error on failure
            logger.error("Error during OCR processing", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def poll_ocr_result(self, operation_id: str) -> ExtractionResult:
        '''Polls Azure Read API until OCR is complete or times out'''

        # Retry loop to poll for result
        attempt = 0
        while attempt < self.max_attempts:
            # it fetches the OCR job status and any results (if available).
            result = await asyncio.to_thread(self.client.get_read_result, operation_id)

            # Success case
            if result.status == OperationStatusCodes.succeeded:
                return self.process_ocr_results(result)

            # Error cases
            elif result.status.lower() in ["failed", "cancelled"]:
                return APIResponse(success=False, message=f"OCR status: {result.status}")

            # Retry after delay
            await asyncio.sleep(self.retry_delay)
            attempt += 1

        # Fallback return if timeout reached
        return self.process_ocr_results(result)


    def process_ocr_results(self, read_result) -> APIResponse:
        '''Processes OCR results to extract patient and test information using medical parser only'''

        try:
            # Extract text data from OCR results
            lines = [line.text for page in read_result.analyze_result.read_results for line in page.lines]
            
            if not lines:
                raise ValueError("No text lines found in OCR results")
            
            line_dicts = [{"text": line} for line in lines]
            full_text = "\n".join(lines)

            logger.debug(f"Extracted {len(lines)} lines, {len(full_text)} characters")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Sample lines: {lines[:5]}")

            # Extract patient metadata using PatientInfoExtractor
            patient_info = self._extract_patient_info(line_dicts)

            # Extract investigations using medical parser only
            investigations = self._extract_investigations_medical_parser(full_text, line_dicts)

            # Create and return unified result
            extraction_result = ExtractionResult(
                patient_information=patient_info,  
                investigations=investigations,
                source="OCR Document",
            )

            logger.info(f"Extracted {len(investigations)} investigations")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Investigations:\n%s", json.dumps(investigations, indent=2))
                
            return extraction_result

        except Exception as e:
            logger.error(f"Error processing OCR results: {str(e)}", exc_info=True)
            return self._create_error_response(e)

    def _extract_patient_info(self, line_dicts: List[Dict]) -> Dict:
        '''Extract patient information using PatientInfoExtractor'''
        try:
            patient_info_extractor = PatientInfoExtractor()
            patient_info = patient_info_extractor.extract_patient_information({"lines": line_dicts})
            
            logger.info(f"Extracted patient info: {patient_info.get('name', 'Unknown')}")
            return patient_info
            
        except Exception as e:
            logger.error(f"Failed to extract patient info: {str(e)}")
            return {}

    def _extract_investigations_medical_parser(self, full_text: str, line_dicts: List[Dict]) -> List[Dict]:
        '''Extract investigations using medical parser only'''
        try:
            # Prepare data for medical parser
            ocr_data = {
                "full_text": full_text,
                "lines": line_dicts
            }
            
            # Extract using medical parser
            parser_result = self.medical_parser.extract_investigations(ocr_data)
            
            # Handle the structured response from medical parser
            if isinstance(parser_result, dict) and parser_result.get("success"):
                investigations = parser_result.get("data", {}).get("investigations", [])
                logger.info(f"Medical parser extracted {len(investigations)} investigations")
                return investigations
            else:
                error_msg = parser_result.get("error", "Unknown error") if isinstance(parser_result, dict) else "Invalid response format"
                logger.error(f"Medical parser failed: {error_msg}")
                return []
                
        except Exception as e:
            logger.error(f"Medical parser failed with exception: {str(e)}", exc_info=True)
            return []

    def _create_error_response(self, error: Exception) -> ExtractionResult:
        '''Create error response for failed processing'''
        return ExtractionResult(
            patient_information={},
            investigations=[],
            source="OCR Document",
            quality_notes=f"Processing failed: {str(error)}"
        )
