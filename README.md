# Medical PDF Text Extraction System

This backend system extracts structured data from multiple uploaded medical PDF reports using Azure OCR API. 
It identifies key fields like patient info, lab test results, etc., by matching them against a predefined template (Excel). 
The results are returned in JSON format and can be easily exported into Excel.



# Features
- Accepts multiple PDF uploads via a REST API or frontend UI.
- Uses Azure’s OCR API to extract text from scanned documents.
- Matches extracted data against fields defined in a hospital-style Excel template.
- Returns the extracted values in structured JSON format.
- Web UI to upload and preview extracted data from PDF files.



## Directory Structure

```plaintext
Question_2/
├── .env                         		# Azure credentials (do not commit)
├── README.md                    		# You're here!
├── requirements.txt             		# Python dependencies

├── app/
│   ├── main.py                  		# FastAPI app with API endpoints
│   ├── config.py                		# Azure/environment config loader
│
│   ├── models.py                		# Pydantic data models for request/response
│
│   ├── services/
│   │   ├── ocr_service.py       		# Azure OCR integration logic
│   │   ├── template_service.py  		# Extracts and maps tests from OCR output
│   │   └── get_test_names.py    		# Reference: test name + field definitions
│
│   ├── utils/
│   │   ├── text_matcher.py      		# Match OCR output to test fields
│   │   ├── medical_parser.py    		# Extracts values, units, flags
│   │   ├── patient_info.py      		# Extract patient details
│   │   └── table_parser.py      		# Parse tables from OCR lines
│
│   ├── static/
│   │   ├── index.html           		# Upload UI
│   │   ├── app.js               		# JS for handling uploads & preview
│   │   └── styles.css           		# Basic CSS styling

├── templates/
│   └── medical_template.xlsx    		# Excel-based field mapping template

├── tests/                        		# Test suite and test data
│   ├── test_queries_used/       		# Sample PDFs & JSON queries
│   └── screenshots/             		# UI/API test screenshots

```

## Getting Started

### 1. Clone the Repository

```bash
https://github.com/Adithya098/Elimai_assessment_Q2.git
```

### 2. Set Up Environment

Create a `.env` file in the root folder with your Azure credentials:

```env
AZURE_OCR_KEY = your_key
AZURE_REGION = your_region
```
3. Install Dependencies
```bash
pip install -r requirements.txt
```
4. Run the App
```bash
python -m uvicorn app.main:app --reload --port 9000
```
Visit the API at: `http://localhost:9000` or open the Web UI at: `http://localhost:9000/static/index.html`.
