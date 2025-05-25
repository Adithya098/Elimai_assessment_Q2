# file : medical_parser.py

'''
Parses OCR text from medical documents to extract structured test results by matching
known test name patterns and extracting relevant values, units, flags, and reference ranges.
'''

import re
import logging
from typing import List, Dict, Optional, Tuple
from app.models import TestResult, InvestigationCategory
from app.services.get_test_names import test_name_fields

logger = logging.getLogger(__name__)

class MedicalTestParser:
    def __init__(self):
        self.units_patterns = {
            'g/dL': r'g\s*/\s*dL|g/dL|gm%',
            '%': r'%|percent',
            'fl': r'fl|fL|femtolit(er|re)s?',
            'pg': r'pg|picograms?',
            'Cells / Cumm': r'cells?\s*/\s*cumm|cells?\s*per\s*cumm',
            'Lakhs / Cumm': r'lakhs?\s*/\s*cumm|lakhs?\s*per\s*cumm',
            'millions / cumm': r'millions?\s*/\s*cumm|millions?\s*per\s*cumm',
            'thousands / cumm': r'thousands?\s*/\s*cumm|thousands?\s*per\s*cumm'
        }

        self.test_patterns = self._build_test_patterns()
        self.valid_categories = set(item.value for item in InvestigationCategory)
        
        # Debug: Log available patterns
        logger.info(f"Built test patterns for categories: {list(self.test_patterns.keys())}")
        for category, patterns in self.test_patterns.items():
            logger.info(f"Category '{category}': {len(patterns)} patterns")
        
        logger.info(f"Valid categories: {self.valid_categories}")

    def _build_test_patterns(self) -> Dict[str, List[Tuple[str, str]]]:
        patterns = {}
        for field in test_name_fields:
            section = field.section.lower()
            if section not in patterns:
                patterns[section] = []
            keywords_re = '|'.join(
                re.escape(keyword).replace(r'\ ', r'\\s+')
                for keyword in field.keywords
            )
            pattern = rf'\b({keywords_re})\b'
            patterns[section].append((pattern, field.field_name))
        return patterns

    def extract_investigations(self, ocr_data: Dict[str, List[Dict]]) -> Dict:
        lines = ocr_data.get("lines", [])
        full_text = ocr_data.get("full_text", "")
        
        logger.info(f"Processing {len(lines)} lines for medical parsing")
        
        investigations = []
        current_category = None
        
        # Keep track of all lines for context-aware parsing
        all_lines = [line_obj.get("text", "").strip() for line_obj in lines]

        for i, line_obj in enumerate(lines):
            line = line_obj.get("text", "").strip()
            if not line:
                continue

            logger.debug(f"Line {i}: {line}")

            # Try detecting category from header lines
            lower_line = line.lower()
            old_category = current_category
            
            # More flexible category detection
            for cat in self.valid_categories:
                if (cat.lower() in lower_line or 
                    any(keyword in lower_line for keyword in [f"{cat}:", f"{cat} test", f"{cat} report", f"{cat} -"])):
                    current_category = cat
                    logger.info(f"Found category '{cat}' in line: {line}")
                    break

            if current_category != old_category:
                logger.info(f"Category changed from {old_category} to {current_category}")

            if not current_category:
                logger.debug(f"No category set, skipping line: {line}")
                continue

            # Match known test patterns under current category
            category_patterns = self.test_patterns.get(current_category, [])
            logger.debug(f"Testing {len(category_patterns)} patterns for category {current_category}")
            
            for pattern, test_name in category_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    logger.info(f"Pattern matched! Test: {test_name}, Line: {line}")
                    
                    # Try to find the actual test result in the next few lines
                    result = self._parse_test_with_context(current_category, test_name, line, all_lines, i)
                    
                    if result:
                        investigations.append(result)
                        logger.info(f"Successfully parsed test: {test_name}")
                    else:
                        logger.warning(f"Failed to parse matched line and context: {line}")
                    break
            else:
                logger.debug(f"No patterns matched for line: {line}")

        logger.info(f"Medical parser extracted {len(investigations)} investigations")
        
        return {
            "success": True,
            "message": "Extraction successful",
            "data": {
                "investigations": investigations,
                "source": "OCR Document",
                "confidence": 0.95
            },
            "error": None
        }

    def _parse_test_with_context(self, category: str, test_name: str, current_line: str, all_lines: List[str], line_index: int) -> Optional[Dict]:
        """Parse test with context from surrounding lines"""
        
        # Try parsing the current line first
        result = self._parse_test_line(category, test_name, current_line)
        if result:
            return result
        
        # If current line doesn't have the value, look in the next few lines
        search_range = min(5, len(all_lines) - line_index - 1)  # Look ahead up to 5 lines
        
        for offset in range(1, search_range + 1):
            if line_index + offset < len(all_lines):
                next_line = all_lines[line_index + offset]
                
                # Try combining current line with next line
                combined_line = f"{current_line} {next_line}"
                result = self._parse_test_line(category, test_name, combined_line)
                if result:
                    logger.debug(f"Found result in combined lines: {combined_line}")
                    return result
                
                # Try parsing just the next line (in case value is on separate line)
                if self._line_contains_numeric_value(next_line):
                    result = self._parse_test_line(category, test_name, f"{test_name}: {next_line}")
                    if result:
                        logger.debug(f"Found result in next line: {next_line}")
                        return result
        
        return None

    def _line_contains_numeric_value(self, line: str) -> bool:
        """Check if line contains a numeric value that could be a test result"""
        return bool(re.search(r'\d+\.?\d*', line))

    def _parse_test_line(self, category: str, test_name: str, line: str) -> Optional[Dict]:
        """Parse a test line to extract value, units, etc."""
        
        logger.debug(f"Parsing line for {test_name}: {line}")
        
        # Multiple parsing patterns to try
        patterns = [
            # Pattern 1: Test Name: Value Units [Range] Flag
            r'(?P<name>.*?)\s*[:\-]\s*(?P<value>\d+\.?\d*)\s*(?P<units>[a-zA-Z%/\.\s]+)?\s*(?P<range>\[?[\d\s\-to\.]+[\-to\s]+[\d\s\.]+[a-zA-Z%/\.\s]*\]?)?\s*(?P<flag>[HL])?',
            
            # Pattern 2: Value Units Flag (when test name is already known)
            r'^\s*(?P<value>\d+\.?\d*)\s*(?P<units>[a-zA-Z%/\.\s]+?)?\s*(?P<range>\[?[\d\s\-to\.]+[\-to\s]+[\d\s\.]+[a-zA-Z%/\.\s]*\]?)?\s*(?P<flag>[HL])?\s*$',
            
            # Pattern 3: Simple Value Units
            r'(?P<value>\d+\.?\d*)\s+(?P<units>[a-zA-Z%/\.]+)\s*(?P<flag>[HL])?',
            
            # Pattern 4: Just Value (minimal case)
            r'(?P<value>\d+\.?\d*)'
        ]

        for i, pattern in enumerate(patterns):
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                logger.debug(f"Pattern {i+1} matched: {match.groupdict()}")
                
                value_str = match.group('value')
                if not value_str:
                    continue
                
                try:
                    value = float(value_str) if '.' in value_str else int(value_str)
                except (ValueError, TypeError):
                    continue
                
                units = match.groupdict().get('units', '') or ""
                units = self._normalize_units(units.strip()) if units else ""
                
                flag = match.groupdict().get('flag', '')
                flag = flag.upper() if flag else None
                
                ref_range = match.groupdict().get('range', '')
                if ref_range:
                    ref_range = re.sub(r'\s*(–|to|−)\s*', ' - ', ref_range.strip('[] '))
                
                result_data = {
                    "value": value,
                    "units": units or None,
                    "reference_range": ref_range or None,
                    "flag": flag,
                    "specimen": "EDTA" if category == "haematology" else "Serum",
                }

                investigation = {
                    "investigation": category,
                    "test_name": self.get_canonical_test_name(test_name),
                    "results": result_data,
                }
                
                logger.debug(f"Successfully created investigation: {investigation}")
                return investigation

        logger.debug(f"No patterns matched for line: {line}")
        return None

    def get_canonical_test_name(self, name: str) -> str:
        """Resolves the canonical name using test_name_fields"""
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
    
    def _normalize_units(self, raw_units: str) -> str:
        if not raw_units:
            return ""
            
        raw_units = raw_units.strip()
        for standard_unit, pattern in self.units_patterns.items():
            if re.search(pattern, raw_units, re.IGNORECASE):
                return standard_unit
        
        # Clean up common unit variations
        cleaned = re.sub(r'\s+', ' ', raw_units)  # normalize spaces
        cleaned = re.sub(r'[^\w/%\-\.]', '', cleaned)  # remove special chars except common unit chars
        
        if cleaned:
            logger.debug(f"Using cleaned unit '{cleaned}' from raw '{raw_units}'")
            return cleaned
        
        logger.warning(f"Unrecognized unit '{raw_units}', returning raw.")
        return raw_units