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
        self.common_units = {
        'g/dL', 'mg/dL', 'ng/mL', 'pg', 'fl', 'IU/L', 'U/L', '%', 
        'Cells/cumm', 'Lakhs/cumm', 'millions/cumm', 'thousands/cumm',
        'mEq/L', 'mmol/L', 'fL', 'g/L', 'mg/L', 'ng/dL', 'pg/mL'
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
        investigations = []
        current_category = None
        all_lines = [line_obj.get("text", "").strip() for line_obj in lines]

        # --- Step 1: Split into blocks between specimens ---
        specimen_keywords = {"EDTA", "URINE", "PLASMA", "SERUM", "WHOLE"}
        blocks = []
        current_block = []

        for line_obj in lines:
            text = line_obj.get("text", "").strip()
            upper_text = text.upper()

            if any(spec in upper_text for spec in specimen_keywords):
                if current_block:
                    blocks.append(current_block)
                current_block = [text]
            else:
                current_block.append(text)

        if current_block:
            blocks.append(current_block)

        logger.info(f"Split OCR lines into {len(blocks)} blocks based on specimen keywords")

        print("\n===== BLOCKS FROM OCR DATA =====")
        for idx, block in enumerate(blocks):
            print(f"\n🧱 Block {idx + 1}:")
            for line in block:
                print(f"   {line}")
            print("─" * 50)
    
        # --- Step 2: Process blocks ---
        for block in blocks:
            block_text = " ".join(block)
            lower_block_text = block_text.lower()

            # Try detecting category from text
            for cat in self.valid_categories:
                if (cat.lower() in lower_block_text or 
                    any(keyword in lower_block_text for keyword in [f"{cat}:", f"{cat} test", f"{cat} report", f"{cat} -"])):
                    current_category = cat
                    logger.info(f"Found category '{cat}' in block: {block[:2]}")
                    break

            if not current_category:
                logger.debug("No category set, skipping block.")
                continue

            category_patterns = self.test_patterns.get(current_category, [])

            for pattern, test_name in category_patterns:
                if re.search(pattern, block_text, re.IGNORECASE):
                    logger.info(f"Pattern matched! Test: {test_name}, Block: {block[:2]}")
                    result = self._parse_test_line(current_category, test_name, block_text)

                    if result:
                        reference_range = self._extract_reference_range(block_text, test_name)
                        result["results"]["reference_range"] = reference_range if reference_range else "Not available"
                        investigations.append(result)
                        logger.info(f"Successfully parsed test: {test_name}")
                    else:
                        logger.warning(f"Failed to parse block: {block[:2]}")
            

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


    def _extract_reference_range(self, text: str, test_name: str) -> Optional[str]:
        """Enhanced reference range extraction that checks for common patterns"""
    
        # First try to find range in standard formats
        range_patterns = [
            r'(?:ref\.?|reference)\s*:\s*([\d\.]+\s*[-–]\s*[\d\.]+)',  # "Ref: 3.5-5.5"
            r'([\d\.]+\s*[-–]\s*[\d\.]+)\s*\(?ref\.?\)?',             # "3.5-5.5 (Ref)"
            r'\(([\d\.]+\s*[-–]\s*[\d\.]+)\)',                        # "(3.5-5.5)"
            r'(?:range|normal)\s*:\s*([\d\.]+\s*[-–]\s*[\d\.]+)',     # "Range: 3.5-5.5"
            r'[\d\.]+\s*[-–]\s*[\d\.]+$',                            # "76 - 96" at end of line
        ]
        
        for pattern in range_patterns:
            match = re.search(pattern, text)
            if match:
                range_text = match.group(1) if len(match.groups()) > 0 else match.group()
                return range_text.strip()
        
        return None

    def _parse_test_with_context(self, category: str, test_name: str, current_line: str, all_lines: List[str], line_index: int) -> Optional[Dict]:
        """Parse test with context from surrounding lines"""
        
        # Combine current line with next 3 lines (where value, units, range typically are)
        combined_lines = [current_line]
        for offset in range(1, 4):
            if line_index + offset < len(all_lines):
                combined_lines.append(all_lines[line_index + offset])
        
        # Try parsing the combined text
        combined_text = " ".join(combined_lines)
        result = self._parse_test_line(category, test_name, combined_text)
        
        if result:
            # If we still didn't get reference range, try extracting from combined text
            if not result.get("results", {}).get("reference_range"):
                ref_range = self._extract_reference_range(combined_text, test_name)
                if ref_range:
                    result["results"]["reference_range"] = ref_range
            return result
        
        return None

    def _parse_test_line(self, category: str, test_name: str, line: str) -> Optional[Dict]:
        """Enhanced test line parser that handles value, units, and reference range in sequence"""
        
        # Pattern to match the common structure: value, units, then range
        pattern = (
            r'(?P<value>\d+\.?\d*)\s*'  # Value
            r'(?P<units>[a-zA-Z%/\.]+(?:\s*/\s*[a-zA-Z]+)?)?\s*'  # Units
            r'(?P<range>[\d\.]+\s*[-–]\s*[\d\.]+)?'  # Reference range
        )
        
        # First try to match the full pattern (value, units, range)
        match = re.search(pattern, line, re.IGNORECASE)
        if not match:
            return None
        
        value_str = match.group('value')
        try:
            value = float(value_str) if '.' in value_str else int(value_str)
        except (ValueError, TypeError):
            return None
        
        # Get raw units and validate against known units
        raw_units = match.group('units')
        units, ref_range_from_units = self._split_units_and_range(raw_units) if raw_units else (None, None)
        
        # Get reference range
        ref_range = match.group('range')
        if not ref_range and ref_range_from_units:
            ref_range = ref_range_from_units
        
        logger.debug(f"Split units and range: -> units='{units}', range='{ref_range}'")
        
        # Extract specimen from original test name line if available
        specimen = self._extract_specimen(line, category)
        
        # Extract flag (H/L) separately as it might appear after value
        flag = self._extract_flag(line, value_str)
        
        return {
            "investigation": category,
            "test_name": self.get_canonical_test_name(test_name),
            "results": {
                "value": value,
                "units": units,
                "reference_range": ref_range,
                "flag": flag,
                "specimen": specimen,
            }
        }

    def _split_units_and_range(self, raw_text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Splits a string containing units and reference range into separate components.
        Handles cases like:
        - 'millions / cummMale: 4.5 - 5.5' → ('millions/cumm', '4.5 - 5.5')
        - 'Lakhs / Cumm 1.5 - 4.0' → ('Lakhs/cumm', '1.5 - 4.0')
        - 'g/dL 3.5-5.5' → ('g/dL', '3.5-5.5')
        """
        
        # First normalize the text by replacing multiple spaces with single space
        normalized_text = ' '.join(raw_text.split())
        
        # Try to find the split point between units and range
        # Look for the first occurrence of a range pattern in the text
        range_match = re.search(r'(\d+\.?\d*\s*[-–]\s*\d+\.?\d*)', normalized_text)
        if not range_match:
            return normalized_text, None
        
        range_start = range_match.start()
        units_part = normalized_text[:range_start].strip()
        range_part = range_match.group(1)
        
        # Clean up the units part by removing any trailing non-unit characters
        # This handles cases like "millions / cummMale:" where "Male:" should be removed
        for unit in sorted(self.common_units, key=lambda x: -len(x)):
            # Compare case-insensitive and ignoring spaces
            if unit.replace(" ", "").lower() in units_part.replace(" ", "").lower():
                # Find the actual unit text in the string (preserving original case)
                unit_pattern = re.escape(unit).replace(r'\ ', r'\s*')
                unit_match = re.search(unit_pattern, units_part, re.IGNORECASE)
                if unit_match:
                    clean_units = unit_match.group()
                    return clean_units, range_part
        
        # If no known unit matched, try to extract reasonable units before the range
        # Split at last non-alphanumeric character before the range
        units_candidate = re.sub(r'[^a-zA-Z/%]', ' ', units_part).strip()
        if units_candidate:
            return units_candidate, range_part
        
        return None, range_part

    def _validate_units(self, raw_units: str) -> Optional[str]:
        """Check if the extracted units are valid known units"""
        if not raw_units:
            return None
        
        # Normalize the units string
        normalized = re.sub(r'\s+', '', raw_units.strip())  # Remove all whitespace
        
        # Check against known units
        for unit in self.common_units:
            if re.fullmatch(unit.replace('/', '\/'), normalized, re.IGNORECASE):
                return unit
        
        # If not found in common units, check if it's actually a range
        if self._looks_like_range(normalized):
            return None
        
        # Return the normalized form if we can't classify it
        return normalized

    def _looks_like_range(self, text: str) -> bool:
        """Determine if text looks like a reference range"""
        return bool(re.match(r'^[\d\.]+\s*[-–]\s*[\d\.]+$', text.strip()))

    def _extract_flag(self, line: str, value_str: str) -> Optional[str]:
        """Extract flag (H/L) that appears near the value"""
        # Look for H/L flags near the value
        flag_match = re.search(
            rf'{re.escape(value_str)}\s*([HL])\b',
            line,
            re.IGNORECASE
        )
        return flag_match.group(1).upper() if flag_match else None


    def _extract_specimen(self, line: str, category: str) -> Optional[str]:
        """Extract specimen anywhere in the line from known keywords"""
        VALID_SPECIMENS = {"EDTA", "SERUM", "PLASMA", "WHOLE", "URINE"}
        line_upper = line.upper()
        for specimen in VALID_SPECIMENS:
            if specimen in line_upper:
                return specimen
        return None
        

    def _line_contains_numeric_value(self, line: str) -> bool:
        """Check if line contains a numeric value that could be a test result"""
        return bool(re.search(r'\d+\.?\d*', line))

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