# file : table_parser.py

'''
TableLineParser class is used to parse individual lines from tabular lab test result data. 
It extracts structured fields like specimen type,
test name, method, numeric result value, flag (high/low), units, and reference
range from text lines using regex patterns. It also normalizes units and cleans
reference range formats while skipping non-data lines such as headers and separators.
'''

import re
from typing import Dict, Optional

class TableLineParser:
    def parse_table_line(self, line: str) -> Optional[Dict]:
        original_line = line
        print(f"🔍 parse_table_line received:\n  {line}")
        
        try:
            # Skip lines that are clearly headers or separators
            if self.should_skip_line(line):
                return None

            # Improved pattern for structured table rows
            # Format: Specimen | Test Name (Method) | Result | Flag Units | Reference Value
            pattern = r"""
                ^\s*(?P<specimen>[A-Za-z]+)?\s*\|?\s*  # Optional specimen
                (?P<test_name>[^|]+?)\s*  # Test name (everything until pipe or next field)
                (?:\s*\((?P<method>[^)]+)\))?\s*  # Optional method in parentheses
                \|?\s*(?P<value>\d+\.?\d*)\s*  # Numeric value
                (?:\|?\s*(?P<flag>[HL])\s*)?  # Optional flag (H/L)
                (?:\|?\s*(?P<units>[^|]+?)\s*)?  # Units (optional)
                (?:\|?\s*(?P<reference_range>[^|]+)\s*)?$  # Reference range (optional)
            """
            
            match = re.search(pattern, line, re.VERBOSE | re.IGNORECASE)
            if not match:
                return None

            groups = match.groupdict()
            
            # Clean and validate extracted fields
            test_name = groups.get('test_name', '').strip()
            if not test_name or len(test_name) < 2:
                return None

            # Extract and process individual fields from the regex groups for further validation and normalization
            value = groups.get('value')
            if not value:
                return None

            units = self.normalize_units(groups.get('units', ''))
            flag = groups.get('flag')
            reference_range = self.clean_reference_range(groups.get('reference_range', ''))
            method = groups.get('method', '').strip() or None
            specimen = groups.get('specimen', '').strip() or None

            parsed_dict = {
                "test_name": test_name,
                "value": value,
                "unit": units,
                "reference_range": reference_range,
                "flag": flag,
                "sample_type": specimen,
                "method": method,
            }
            
            print(f"✅ Parsed result:\n  {parsed_dict}")
            return parsed_dict

        except Exception as e:
            print(f"Error parsing line: {e}")
            return None

    def should_skip_line(self, line: str) -> bool:
        """Skip header lines, separators, etc."""
        line = line.strip().lower()
        if not line:
            return True
        if line.startswith(('specimen', 'test name', 'result', 'reference')):  # Header lines
            return True
        if line.startswith(('---', '===', '___', '|||')):  # Separators
            return True
        if all(c in '-=| ' for c in line):  # Lines with only separators
            return True
        return False

    def normalize_units(self, raw_units: str) -> Optional[str]:
        """Normalize unit strings"""
        if not raw_units:
            return None
            
        raw_units = raw_units.strip()
        unit_mappings = {
            'g/dl': 'g/dL',
            'pg': 'pg',
            'fl': 'fl',
            '%': '%',
            'cells/cumm': 'Cells / Cumm',
            'lakhs/cumm': 'Lakhs / Cumm',
            'millions/cumm': 'millions / cumm',
            'thousands/cumm': 'thousands / cumm',
            'mm/hr': 'mm/hr'
        }
        
        # Try exact match first
        lower_units = raw_units.lower()
        for unit, standard in unit_mappings.items():
            if unit in lower_units:
                return standard
                
        # Fallback to cleaning
        cleaned = re.sub(r'\s+', ' ', raw_units)  # Normalize spaces
        cleaned = re.sub(r'[^\w/%]', '', cleaned)  # Remove special chars
        return cleaned or None

    def clean_reference_range(self, raw_range: str) -> Optional[str]:
        """Clean up reference range strings"""
        if not raw_range:
            return None
            
        # Remove gender prefixes if they exist
        cleaned = re.sub(r'^(Male|Female)\s*[:]?\s*', '', raw_range.strip(), flags=re.IGNORECASE)
        # Normalize separators
        cleaned = re.sub(r'\s*(to|-|–)\s*', ' - ', cleaned)
        return cleaned or None