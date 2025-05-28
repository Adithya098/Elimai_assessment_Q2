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
from app.services.template_service import TemplateService
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
        '''Processes OCR results to extract patient and test information'''

        # Collect all lines from OCR output
        lines = [line.text for page in read_result.analyze_result.read_results for line in page.lines]
        line_dicts = [{"text": line} for line in lines]
        full_text = "\n".join(lines)

        '''
        # Log some diagnostic output
        logger.debug(f"Full OCR text extracted ({len(full_text)} characters)")
        logger.info(f"Sample OCR lines: {lines[:10]}")
        '''
        
        # Extract patient metadata
        # patient_info = self.extract_patient_info_simplified(full_text)
        
        # Extract patient metadata using PatientInfoExtractor from 'patient_info.py'
        patient_info_extractor = PatientInfoExtractor()
        patient_info = patient_info_extractor.extract_patient_information({"lines": [{"text": line} for line in lines]})

        # Extract tests using template parser
        template_parser = TemplateService(settings.TEMPLATE_PATH)
        investigations_template = template_parser.extract_investigations(full_text)

        # Extract using medical keyword parser
        investigations_medical_raw = self.medical_parser.extract_investigations({
            "full_text": full_text,
            "lines": line_dicts
        })

        # Normalize parser return value
        if isinstance(investigations_medical_raw, dict):
            investigations_medical = investigations_medical_raw.get("data", {}).get("investigations", [])
        else:
            logger.error(f"Medical parser returned unexpected type: {type(investigations_medical_raw)}")
            investigations_medical = []

        # Extract from tabular test lines
        investigations_table = self.extract_table_investigations(read_result)

        # Combine all investigations into one list
        investigations = self.merge_investigation_results(
            medical_results=investigations_medical + investigations_template,
            table_results=investigations_table
        )

        # Return unified result object
        extraction_result = ExtractionResult(
            patient_information=patient_info,  
            investigations=investigations,
            source="OCR Document",
            quality_notes=None
        )

        logger.info("Extracted Investigations:\n%s", json.dumps(investigations, indent=2))
        return extraction_result

    '''
    def extract_patient_info_simplified(self, text: str) -> Dict[str, str]:
        #Uses regex patterns to extract patient information from text

        # Define patterns to match patient metadata
        patterns = {
            'patient_name': r'patient\s*name\s*[:\-]?\s*([A-Za-z\s\.]+)',
            'age_sex': r'age\s*/\s*sex\s*[:\-]?\s*(\d+)[\sYy]*[/\s]*([MF])',
            'patient_id': r'patient\s*id\s*[:\-]?\s*([A-Za-z0-9]+)',
            'sid_no': r'sid\s*no\s*[:\-]?\s*([A-Za-z0-9]+)',
            'collected_date': r'collected\s*(?:on|date)\s*[:\-]?\s*([\d/\\\s:-]+)',
            'reported_date': r'reported\s*(?:on|date)\s*[:\-]?\s*([\d/\\\s:-]+)',
            'ref_by': r'ref(?:erred)?\s*by\s*[:\-]?\s*([A-Za-z\s\.]+)'
        }

        # Store extracted fields
        info = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Special handling for age/sex combined field
                if key == 'age_sex':
                    age, sex = match.groups()
                    info[key] = f"{age.strip()} {sex.upper()}"
                else:
                    value = match.group(1).strip()
                    # Clean up date fields
                    if key in ['collected_date', 'reported_date']:
                        value = re.sub(r'[\d]{1,2}:[\d]{2}([:\d]*)', '', value).strip()
                        value = value[:-2]
                    info[key] = value.split("\n")[0].strip()
        return info
    '''
    
    def extract_table_investigations(self, read_result) -> List[Dict]:
        '''Extracts investigations from table-formatted OCR lines'''

        # Initialize output and specimen context
        structured_investigations = []
        current_specimen = None

        # Flatten all lines
        all_lines = []
        for page in read_result.analyze_result.read_results:
            for line in page.lines:
                all_lines.append(line.text.strip())

        logger.info(f"Table parser processing {len(all_lines)} lines")

        for line in all_lines:
            # Skip blank lines
            if not line.strip():
                continue

            # Detect specimen types like EDTA, Serum, etc.
            specimen_match = re.match(r'^\s*(EDTA|Serum|Plasma|Urine|Cit\.?\s?Blood)\b', line, re.IGNORECASE)
            if specimen_match:
                current_specimen = specimen_match.group(0)
                logger.debug(f"Found specimen: {current_specimen}")
                continue

            # Parse table line
            parsed = self.table_parser.parse_table_line(line)
            if parsed:
                # Set specimen if not already present
                if current_specimen and not parsed.get('sample_type'):
                    parsed['sample_type'] = current_specimen

                # Validate parsed test
                if self.is_valid_investigation(parsed):
                    investigation = self.convert_table_result_to_investigation(parsed)
                    if investigation:
                        structured_investigations.append(investigation)
                        logger.info(f"Added investigation: {investigation}")

        logger.info(f"Total table investigations found: {len(structured_investigations)}")
        return structured_investigations

    def is_valid_investigation(self, parsed: Dict) -> bool:
        '''Validates a parsed investigation result'''

        # Ensure essential fields are present
        required_fields = ['test_name', 'value']
        for field in required_fields:
            if not parsed.get(field):
                logger.debug(f"Missing required field {field} in: {parsed}")
                return False

        # Validate test name
        test_name = parsed['test_name'].strip()
        if len(test_name) < 2 or not any(c.isalpha() for c in test_name):
            logger.debug(f"Invalid test name: {test_name}")
            return False

        # Validate numeric value
        value_str = str(parsed['value']).strip()
        if not value_str:
            logger.debug(f"Empty value: {parsed['value']}")
            return False

        try:
            float(value_str)
        except (ValueError, TypeError):
            logger.debug(f"Invalid value format: {parsed['value']}")
            return False

        return True


    def convert_table_result_to_investigation(self, parsed: Dict) -> Dict:
        try:
            # Handle both direct values and nested "latest" values
            if 'latest' in parsed.get('results', {}):
                # Handle nested "latest" structure
                result_data = parsed['results']['latest']
                value = result_data.get('value')
                units = result_data.get('units')
                flag = result_data.get('flag')
                reference_range = result_data.get('reference_range')
                method = result_data.get('method')
                specimen = result_data.get('specimen')
            else:
                # Handle flat structure
                value = parsed.get('value')
                units = parsed.get('unit')  # Note: some use 'unit' vs 'units'
                flag = parsed.get('flag')
                reference_range = parsed.get('reference_range')
                method = parsed.get('method')
                specimen = parsed.get('sample_type')

            # Convert value to float if possible
            try:
                value = float(value) if value is not None else None
            except (ValueError, TypeError):
                value = None

            return {
                "investigation": "haematology",  # or make dynamic if needed
                "test_name": parsed.get('test_name', '').strip(),
                "results": {
                    "value": value,
                    "units": units,
                    "flag": flag,
                    "reference_range": reference_range,
                    "method": method,
                    "specimen": specimen
                }
            }
        except Exception as e:
            logger.warning(f"⚠️ Failed to convert investigation: {parsed} | Error: {e}")
            return None


    @staticmethod
    def normalize_test_name(name: str) -> str:
        return re.sub(r'\W+', '', name).lower()

    @staticmethod
    def normalize_value(value) -> str:
        """Round and stringify value for deduplication comparison"""
        try:
            return str(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        except:
            return str(value)

    def merge_investigation_results(self, medical_results: List[Dict], table_results: List[Dict]) -> List[Dict]:
        logger.info(f"Merging results - Medical: {len(medical_results)}, Table: {len(table_results)}")

        normalized_results = []

        for inv in medical_results + table_results:
            try:
                # Normalize "latest" format if present
                if 'latest' in inv.get('results', {}):
                    normalized = {
                        "investigation": inv.get('investigation', 'haematology'),
                        "test_name": inv.get('test_name', ''),
                        "results": {
                            "value": inv['results']['latest'].get('value'),
                            "units": inv['results']['latest'].get('units'),
                            "flag": inv['results']['latest'].get('flag'),
                            "reference_range": inv['results']['latest'].get('reference_range'),
                            "method": inv['results']['latest'].get('method'),
                            "specimen": inv['results']['latest'].get('specimen')
                        }
                    }
                else:
                    normalized = {
                        "investigation": inv.get('investigation', 'haematology'),
                        "test_name": inv.get('test_name', ''),
                        "results": inv.get('results', {})
                    }

                # Ensure valid
                if normalized['test_name'] and normalized['results'].get('value') is not None:
                    normalized_results.append(normalized)

            except Exception as e:
                logger.warning(f"Skipping invalid investigation during merge: {inv} - {str(e)}")

        # Deduplication using normalized test_name and rounded value
        merged = {}
        for inv in normalized_results:
            # More aggressive normalization
            test_name = self.get_canonical_test_name(inv['test_name'])
            value_key = self.normalize_value(inv['results'].get('value'))
            
            # Group by canonical name + value
            dedup_key = f"{test_name}:{value_key}"
            
            if dedup_key not in merged:
                merged[dedup_key] = inv
            else:
                # Merge to keep most complete version
                existing = merged[dedup_key]['results']
                new = inv['results']
                for key in ['units', 'flag', 'reference_range', 'method', 'specimen']:
                    if not existing.get(key) and new.get(key):
                        existing[key] = new[key]
                        
        return list(merged.values())


    def get_canonical_test_name(self, name: str) -> str:
        """Map keyword or variant to canonical test name using test_name_fields."""
        name_clean = re.sub(r'[^a-z0-9]', '', name.lower())
    
        for field in test_name_fields:
            # Check against field name
            field_clean = re.sub(r'[^a-z0-9]', '', field.field_name.lower())
            if name_clean == field_clean:
                return field.field_name
                
            # Check against all keywords
            for kw in field.keywords:
                kw_clean = re.sub(r'[^a-z0-9]', '', kw.lower())
                if name_clean == kw_clean:
                    return field.field_name
                    
        return name
