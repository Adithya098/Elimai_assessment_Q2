from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from enum import Enum
import re

class InvestigationCategory(str, Enum):
    # Enum for different categories of medical investigations
    HAEMATOLOGY = 'haematology'
    BIOCHEMISTRY = 'biochemistry'
    MICROBIOLOGY = 'microbiology'
    SEROLOGY = 'serology'
    IMMUNOLOGY = 'immunology'
    CLINICAL_PATHOLOGY = 'clinical pathology'


class TestResult(BaseModel):
    # Model to represent a test result with value, units, method, etc.
    value: Optional[Union[str, float, int]] = None
    units: Optional[str] = None
    reference_range: Optional[str] = None
    flag: Optional[str] = None
    specimen: Optional[str] = None

    @field_validator('value', mode='before')
    def parse_value(cls, v):
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return str(v)

    @model_validator(mode='before')
    def move_result_to_value(cls, values):
        if 'result' in values and 'value' not in values:
            values['value'] = values.pop('result')
        return values
    
    
class TemplateField(BaseModel):
    # Represents a single field in a template with metadata
    field_name: str
    keywords: List[str]
    field_type: str
    section: str


class Template(BaseModel):
    # Model describing a template with patient and investigation fields
    template_name: str
    patient_fields: List[TemplateField]
    investigation_fields: List[TemplateField]
    date_columns: List[str]


class PatientInformation(BaseModel):
    # Contains extracted patient details from reports
    patient_name: Optional[str] = Field(default="Not Provided")
    age_sex: Optional[str] = Field(default="Not Provided")
    patient_id: Optional[str] = Field(default="Not Provided")
    sid_no: Optional[str] = Field(default="Not Provided")
    collected_date: Optional[str] = Field(default="Not Provided")
    reported_date: Optional[str] = Field(default="Not Provided")
    ref_by: Optional[str] = Field(default="Not Provided")


class Investigation(BaseModel):
    # Represents a medical investigation with category, test name, and results
    investigation: InvestigationCategory  # Changed to use Enum directly
    test_name: str
    results: TestResult  # Simplified from Dict[str, TestResult] based on logs

    @model_validator(mode='before')
    def transform_results(cls, values):
        if isinstance(values, dict):
            # Handle case where results comes as a dict
            if 'results' in values and isinstance(values['results'], dict):
                values['results'] = TestResult(**values['results'])
        return values


class ExtractionResult(BaseModel):
    # Aggregates patient info and list of investigations from extraction
    patient_information: PatientInformation
    investigations: List[Investigation] = Field(default_factory=list)
    source: str = "OCR Document"
    warnings: List[str] = Field(default_factory=list)  # Added to track validation issues

    @model_validator(mode='before')
    def handle_invalid_investigations(cls, values):
        # Validate and transform raw investigations data into Investigation models,
        # filtering out invalid entries and collecting warnings for any skipped items.
        if isinstance(values, dict):
            valid_investigations = []
            warnings = []
            
            for inv in values.get('investigations', []):
                try:
                    if isinstance(inv, dict):
                        # Handle the structure seen in your logs
                        if 'results' in inv and isinstance(inv['results'], dict):
                            valid_investigations.append(Investigation(
                                investigation=inv['investigation'],
                                test_name=inv['test_name'],
                                results=TestResult(**inv['results'])
                            ))
                        else:
                            # Fallback for other structures
                            valid_investigations.append(Investigation(**inv))
                except Exception as e:
                    warnings.append(f"Skipped investigation {inv.get('test_name')}: {str(e)}")
            
            values['investigations'] = valid_investigations
            if warnings:
                values.setdefault('warnings', []).extend(warnings)
        
        return values


class APIResponse(BaseModel):
    # Standard API response format with success flag, data, and errors
    success: bool
    message: str
    data: Optional[Union[ExtractionResult, List[ExtractionResult], Dict[str, Any]]] = None
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)  # Added to surface validation warnings

    class Config:
        extra = "allow"


class HealthCheckResponse(BaseModel):
    # Health check status response for API monitoring
    status: str = "healthy"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0.0"


class TemplateResponse(BaseModel):
    # Response containing template details for UI or API clients
    template_name: str
    patient_fields: List[Dict[str, Any]]
    investigation_fields: List[Dict[str, Any]]
    date_columns: List[str]


class ErrorResponse(BaseModel):
    # Standard error response model for API errors
    success: bool = False
    message: str
    error: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ValidationErrorResponse(BaseModel):
    # Error response specifically for validation failures
    success: bool = False
    message: str = "Validation error"
    errors: List[Dict[str, Any]]
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())