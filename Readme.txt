# Question 2 : Medical PDF OCR Extraction Backend

This backend system extracts structured data from multiple uploaded medical PDF reports using Azure OCR API. 
It identifies key fields like patient info, lab test results, etc., by matching them against a predefined template (Excel). 
The results are returned in JSON format and can be easily exported into Excel.

---

# Features
- Accepts multiple PDF uploads via a REST API or frontend UI.
- Uses Azure’s OCR API to extract text from scanned documents.
- Matches extracted data against fields defined in a hospital-style Excel template.
- Returns the extracted values in structured JSON format.
- Web UI to upload and preview extracted data from PDF files.


# Project structure:

Question_2/
├── app/
│   ├── main.py                   # FastAPI app with API endpoints
│   ├── config.py                 # Configuration (e.g., Azure credentials)
│   ├── models.py                 # Pydantic data models
│   ├── services/
│   │   ├── ocr_service.py        # Azure OCR integration
│   │   └── template_service.py   # Test data mapping & extraction logic
│   │   └── get_test_names.py     # contains test names with test details
│   ├── utils/
│   │   ├── text_matcher.py       # Match OCR output to test fields
│   │   ├── medical_parser.py     # Parse test results (e.g., values, units)
│   │   └── patient_info.py       # Extract patient info from OCR text
│   │   └── table_parser.py       # Parse tabular lab test data from OCR'd text lines
│   ├── static/
│   │   ├── index.html            # Web frontend for PDF upload
│   │   ├── app.js                # JS for handling uploads
│   │   └── styles.css            # Basic styling
├── templates/
│   └── medical_template.xlsx     # Excel file defining medical test fields
├── tests/                         # Postman test cases & documentation
│   ├── test_queries_used/         # Sample JSON/PDF files for API requests
│   ├── screenshots/              # UI/API screenshots for documentation
├── requirements.txt              # Python dependencies
├── .env                          # Azure credentials (do not commit)
└── README.md                     # You're here!


Go to parent folder (outside app folder) and execute:
	python -m uvicorn app.main:app --reload --port 9000