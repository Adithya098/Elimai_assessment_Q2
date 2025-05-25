# file: template_service.py

'''
This file defines the TemplateService class responsible for:
1. Loading and validating an Excel template with medical test definitions.
2. Extracting patient information from OCR text using regex.
3. Extracting structured investigation results from OCR text based on the template.
'''

import pandas as pd
import re
from typing import Dict, List, Optional, Union
from pathlib import Path
import logging
from datetime import datetime

# Configure logging for the module
logger = logging.getLogger(__name__)

class TemplateService:
    def __init__(self, template_path: Union[str, Path]):
        # Initialize TemplateService with the path to the template Excel file
        self.template_path = Path(template_path)
        self.template_df = self.load_template()
        print("🟡 Loaded columns:", self.template_df.columns.tolist())
        self.validate_template()

    def load_template(self) -> pd.DataFrame:
        '''Load and preprocess the template Excel file.'''
        try:
            # Read all sheets in the Excel file starting from the 10th row
            xls = pd.ExcelFile(self.template_path)
            dfs = []
            
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, header=9)  
                dfs.append(df)
            
            # Combine dataframes and clean column names and string fields
            combined_df = pd.concat(dfs, ignore_index=True)
            combined_df.columns = combined_df.columns.str.strip().str.lower().str.replace(' ', '_')
            combined_df = combined_df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            return combined_df.dropna(how='all')

        except Exception as e:
            # Log and re-raise error if template loading fails
            logger.error(f"Error loading template: {e}")
            raise

    def validate_template(self) -> None:
        '''Validate that required columns exist in the template.'''
        # Ensure the essential columns are present in the loaded template
        required_columns = {'specimen', 'test_name', 'result', 'units', 'reference_value'}
        missing = required_columns - set(self.template_df.columns)
        if missing:
            raise ValueError(f"Template missing required columns: {missing}")

    def extract_patient_info(self, text: str) -> Dict[str, Optional[str]]:
        '''
        Extract patient information from OCR text using flexible pattern matching.
        '''
        # Define regex patterns for extracting patient metadata
        patterns = {
            'patient_name': r"(?:patient name\.?|name\s*[:])\s*([A-Za-z0-9 ./-]+)",
            'age_sex': r"(?:age/sex\.?|age\s*[:])\s*([\d]+)\s*(?:Y|Years?)\s*([MF])",
            'patient_id': r"(?:patient id|id\s*[:])\s*([A-Za-z0-9-]+)",
            'sid_no': r"(?:sid no\.?|sid\s*[:])\s*([A-Za-z0-9-]+)",  # Updated for SID No
            'collected_date': r"(?:collected date|date collected)\s*[:]?\s*([\d/]+)",
            'reported_date': r"(?:reported date|date reported)\s*[:]?\s*([\d/]+)",
            'ref_by': r"(?:ref by|referred by)\s*[:]?\s*([A-Za-z0-9 .-]+)"
        }

        info = {}
        # Search text using the above patterns
        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if field == 'age_sex':
                    age, sex = match.groups()
                    info[field] = f"{age} Y {sex}"
                else:
                    info[field] = match.group(1).strip()
        
        return info

    def extract_investigations(self, text: str) -> List[Dict]:
        '''
        Extract medical test results from OCR text using the template.
        '''
        # Initialize list to hold investigation results
        results = []
        
        # Iterate through the template to match test names in the OCR text
        for _, row in self.template_df.iterrows():
            test_name = str(row['test_name']).strip()
            specimen = str(row['specimen']).strip()
            units = str(row['units']).strip()
            reference_value = str(row['reference_value']).strip()

            # Create a regex pattern for extracting test results
            pattern = (
                fr"{re.escape(test_name)}"
                fr"(?:\s*\(.*?\))?\s*"
                fr"[\s:]*([\d.]+)\s*"
                fr"(?:\s*([LH])\s*)?"
                fr"(?:\s*{re.escape(units)}\s*)?"
            )
            
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue

            try:
                value = float(match.group(1))
                flag = match.group(2) if match.group(2) else None

                # Build structured result entry
                result = {
                    "investigation": row.get('category', 'haematology'),
                    "test_name": test_name,
                    "results": {
                        "latest": {
                            "value": value,
                            "units": units,
                            "flag": flag,
                            "reference_range": reference_value,
                            "specimen": specimen,
                            "method": str(row.get('method', '')).strip()
                        }
                    }
                }
                results.append(result)
                
            except (ValueError, AttributeError) as e:
                # Log warning if parsing fails for a test
                logger.warning(f"Failed to parse value for {test_name}: {e}")
                continue
                
        return results

    def process_report(self, ocr_text: str) -> Dict:
        '''Process complete report and return structured data.'''
        # Return both patient info and investigations as a dictionary
        return {
            "patient_information": self.extract_patient_info(ocr_text),
            "investigations": self.extract_investigations(ocr_text)
        }
