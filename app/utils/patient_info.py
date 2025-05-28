# file : patient_info.py
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
        # Simplified and more precise patterns for extracting patient information
        self.patterns = {
            'patient_name': [
                r'patient\s*name\s*[:\-]?\s*([A-Za-z\s\.]+?)(?=\n|$)',
                r'name\s*of\s*patient\s*[:\-]?\s*([A-Za-z\s\.]+?)(?=\n|$)',
                r'name\s*[:\-]?\s*([A-Za-z\s\.]+?)(?=\n|$)'
            ],
            'age_sex': [
                r'age\s*/\s*sex\s*[:\-]?\s*(\d+)[\sYy]*[/\s]*([MF])',
                r'age/sex\s*[:\-]?\s*(\d+)\s*(?:y|yr|yrs|years?)\s*[/\|]\s*([mfMF])',
                r'(\d+)\s*(?:y|yr|yrs|years?)\s*[/\|]\s*([mfMF])',
                r'age\s*[:\-]?\s*(\d+)\s*(?:y|yr|yrs|years?).*?sex\s*[:\-]?\s*([mfMF])'
            ],
            'patient_id': [
                r'patient\s*id\s*[:\-]?\s*([A-Za-z0-9]+)',
                r'id\s*[:\-]?\s*([A-Za-z0-9]+)',
                r'registration\s*no\s*[:\-]?\s*([A-Za-z0-9]+)'
            ],
            'sid_no': [
                r'sid\s*no?\s*[:\-]?\s*([A-Za-z0-9]+)',
                r'hospital\s*id\s*[:\-]?\s*([A-Za-z0-9]+)',
                r'unique\s*health\s*id\s*[:\-]?\s*([A-Za-z0-9]+)'
            ],
            'collected_date': [
                r'collected\s*(?:on|date)\s*[:\-]?\s*([\d/\-\s:]+)',
                r'collection\s*date\s*[:\-]?\s*([\d/\-\s:]+)',
                r'sample\s*date\s*[:\-]?\s*([\d/\-\s:]+)'
            ],
            'reported_date': [
                r'reported\s*(?:on|date)\s*[:\-]?\s*([\d/\-\s:]+)',
                r'report\s*date\s*[:\-]?\s*([\d/\-\s:]+)',
                r'date\s*of\s*report\s*[:\-]?\s*([\d/\-\s:]+)'
            ],
            'ref_by': [
                r'ref(?:erred)?\s*by\s*[:\-]?\s*([A-Za-z\s\.]+?)(?=\n|$)',
                r'doctor\s*[:\-]?\s*([A-Za-z\s\.]+?)(?=\n|$)'
            ]
        }

    def extract_patient_information(self, ocr_data: Dict[str, List[Dict]]) -> Dict[str, str]:
        '''Extracts patient info from OCR data by matching text patterns and returns flat dictionary.'''
        lines = [line_obj.get("text", "") for line_obj in ocr_data.get("lines", [])]
        full_text = "\n".join(lines)
        
        # Extract each field and build flat dictionary
        info = {}
        
        # Extract patient name
        patient_name = self._extract_field('patient_name', full_text)
        if patient_name:
            info['patient_name'] = self._clean_text_field(patient_name)
        
        # Extract age/sex with simplified handling
        age_sex = self._extract_age_sex(full_text)
        if age_sex:
            info['age_sex'] = age_sex
        
        # Extract patient ID
        patient_id = self._extract_field('patient_id', full_text)
        if patient_id:
            info['patient_id'] = self._clean_text_field(patient_id)
        
        # Extract SID number
        sid_no = self._extract_field('sid_no', full_text)
        if sid_no:
            info['sid_no'] = self._clean_text_field(sid_no)
        
        # Extract and clean up collected date
        collected_date = self._extract_field('collected_date', full_text)
        if collected_date:
            cleaned_date = self._clean_date_field(collected_date)
            parsed_date = self._parse_date(cleaned_date)
            info['collected_date'] = parsed_date if parsed_date else cleaned_date
        
        # Extract and clean up reported date
        reported_date = self._extract_field('reported_date', full_text)
        if reported_date:
            cleaned_date = self._clean_date_field(reported_date)
            parsed_date = self._parse_date(cleaned_date)
            info['reported_date'] = parsed_date if parsed_date else cleaned_date
        
        # Extract referring doctor
        ref_by = self._extract_field('ref_by', full_text)
        if ref_by:
            info['ref_by'] = self._clean_text_field(ref_by)
        
        return info

    def _extract_field(self, field_name: str, text: str) -> Optional[str]:
        '''Extracts a specific patient field from text using regex patterns for that field.'''
        for pattern in self.patterns.get(field_name, []):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip() if match.groups() else match.group(0).strip()
        return None
    
    def _extract_age_sex(self, text: str) -> Optional[str]:
        '''Extracts age and sex information from text and formats it consistently.'''
        for pattern in self.patterns['age_sex']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    age = groups[0].strip()
                    sex = groups[1].strip().upper()
                    
                    # Normalize sex values
                    if sex.lower() in ['male', 'm']:
                        sex = 'M'
                    elif sex.lower() in ['female', 'f']:
                        sex = 'F'
                    
                    return f"{age} Y {sex}"
        return None
    
    def _clean_text_field(self, text: str) -> str:
        '''Cleans up extracted text fields by removing extra whitespace and taking first line.'''
        if not text:
            return ""
        return text.split("\n")[0].strip()
    
    def _clean_date_field(self, date_str: str) -> str:
        '''Cleans up date fields by removing time components, extra spaces, and trimming unwanted characters.'''
        if not date_str:
            return ""
        
        # Remove time components (HH:MM:SS patterns)
        cleaned = re.sub(r'[\d]{1,2}:[\d]{2}([:\d]*)', '', date_str).strip()
        
        # Remove trailing unwanted characters (like extra spaces or slashes)
        if cleaned.endswith(" /"):
            cleaned = cleaned[:-2].strip()  # Remove last 2 characters (space and slash)
        elif cleaned.endswith("/"):
            cleaned = cleaned[:-1].strip()  # Remove just the trailing slash
        
        # Remove trailing double spaces if any
        if len(cleaned) >= 2 and cleaned.endswith('  '):
            cleaned = cleaned[:-2]
        
        return self._clean_text_field(cleaned)
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        '''Parses and standardizes date strings into DD/MM/YYYY format, if possible.'''
        if not date_str:
            return None
        
        try:
            # Support several date formats
            for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y'):
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime('%d/%m/%Y')
                except ValueError:
                    continue
            return date_str  # Return as-is if no known format matches
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {str(e)}")
            return date_str