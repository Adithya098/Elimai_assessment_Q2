# file : text_matcher.py

'''
This class helps unify extraction of patient information and medical investigations
by delegating to specialized extractor classes.
'''

from app.utils.patient_info import PatientInfoExtractor
from app.utils.medical_parser import MedicalTestParser

class TextMatcher:
    def __init__(self):
        # Initialize extractors for patient info and medical tests
        self.patient_info_matcher = PatientInfoExtractor()
        self.medications_investigations_extractor = MedicalTestParser()

    def extract_patient_info(self, *args, **kwargs):
        '''Delegate patient info extraction to PatientInfoExtractor'''
        return self.patient_info_matcher.extract_patient_info(*args, **kwargs)

    def extract_investigations(self, *args, **kwargs):
        '''Delegate investigations extraction to MedicalTestParser'''
        return self.medications_investigations_extractor.extract_investigations(*args, **kwargs)
