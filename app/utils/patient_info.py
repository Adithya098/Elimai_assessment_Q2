# file : patient_info_extractor.py
'''
The PatientInfoExtractor class extracts patient information like name, age, sex, patient IDs, 
collection and report dates, and referring doctor from OCR-extracted text lines using regex patterns. 
It also normalizes and formats some of the fields such as dates and age/sex.
'''

import re
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PatientInfoExtractor:
    def __init__(self):
        # Patterns for extracting patient information using regular expressions
        self.patterns = {
            'patient_name': [
                r'patient\s*name[:-\s]*(.*?)(?=\n|$)',
                r'name\s*of\s*patient[:-\s]*(.*?)(?=\n|$)',
                r'name[:-\s]*(.*?)(?=\n|$)'
            ],
            'age_sex': [
                r'age/sex[:-\s]*(.*?)(?=\n|$)',
                r'age\s*[:-\s]*(\d+)\s*(y|yr|yrs|years?)\s*[/\|]\s*([mf])',
                r'(\d+)\s*(y|yr|yrs|years?)\s*[/\|]\s*([mf])'
            ],
            'patient_id': [
                r'patient\s*id[:-\s]*(\w+)',
                r'id\s*[:-\s]*(\w+)',
                r'registration\s*no[:-\s]*(\w+)'
            ],
            'sid_no': [
                r'sid\s*[:-\s]*(\w+)',
                r'hospital\s*id\s*[:-\s]*(\w+)',
                r'unique\s*health\s*id\s*[:-\s]*(\w+)'
            ],
            'collected_date': [
                r'collected\s*on\s*[:-\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'collection\s*date\s*[:-\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'sample\s*date\s*[:-\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
            ],
            'reported_date': [
                r'reported\s*on\s*[:-\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'report\s*date\s*[:-\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'date\s*of\s*report\s*[:-\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
            ],
            'ref_by': [
                r'referred\s*by\s*[:-\s]*(.*?)(?=\n|$)',
                r'ref\s*by\s*[:-\s]*(.*?)(?=\n|$)',
                r'doctor\s*[:-\s]*(.*?)(?=\n|$)'
            ]
        }


    def extract_patient_info(self, ocr_data: Dict[str, List[Dict]]) -> Dict:
        '''Extracts patient info from OCR data by matching text patterns and returns structured info.'''
        lines = [line_obj.get("text", "") for line_obj in ocr_data.get("lines", [])]
        full_text = "\n".join(lines)
        
        patient_info = {
            "patient_name": self._extract_field('patient_name', full_text),
            "age_sex": self._format_age_sex(self._extract_age_sex(full_text)),
            "patient_id": self._extract_field('patient_id', full_text),
            "sid_no": self._extract_field('sid_no', full_text),
            "collected_date": self._parse_date(self._extract_field('collected_date', full_text)),
            "reported_date": self._parse_date(self._extract_field('reported_date', full_text)),
            "ref_by": self._extract_field('ref_by', full_text)
        }
        
        return {
            "success": True,
            "message": "Extraction successful",
            "data": {
                "patient_information": patient_info
            },
            "error": None
        }


    def _extract_field(self, field_name: str, text: str) -> Optional[str]:
        '''Extracts a specific patient field from text using regex patterns for that field.'''
        for pattern in self.patterns.get(field_name, []):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip() if match.groups() else match.group(0).strip()
        return None
    

    def _extract_age_sex(self, text: str) -> Optional[Dict]:
        '''Extracts age and sex information from text using regex patterns with multiple formats.'''
        for pattern in self.patterns['age_sex']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if len(match.groups()) == 3:
                    return {
                        'age': match.group(1),
                        'age_unit': match.group(2),
                        'sex': match.group(3).upper()
                    }
                elif len(match.groups()) == 1:
                    # Handle cases like "Age/Sex: 25Y/M"
                    parts = re.split(r'[/\|]', match.group(1))
                    if len(parts) >= 2:
                        age_part = re.search(r'(\d+)\s*(y|yr|yrs|years?)', parts[0], re.IGNORECASE)
                        sex_part = re.search(r'([mf])', parts[1], re.IGNORECASE)
                        if age_part and sex_part:
                            return {
                                'age': age_part.group(1),
                                'age_unit': age_part.group(2),
                                'sex': sex_part.group(1).upper()
                            }
        return None
    

    def _format_age_sex(self, age_sex: Optional[Dict]) -> Optional[str]:
        '''Formats age and sex dictionary into a standardized string representation.'''
        if not age_sex:
            return None
        return f"{age_sex['age']} {age_sex['age_unit'].upper()} {age_sex['sex']}"
    
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        '''Parses and standardizes date strings into DD/MM/YYYY format, if possible.'''
        if not date_str:
            return None
        
        try:
            # Support several date formats
            for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y'):
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    continue
            return date_str  # Return as-is if no known format matches
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {str(e)}")
            return date_str
    
