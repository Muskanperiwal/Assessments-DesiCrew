"""Pydantic schemas mapping the required fields for all 10 document types in Task 3."""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class FieldExtraction(BaseModel):
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    method: str

class BaseDocumentSchema(BaseModel):
    document_filename: str
    document_type: str
    classification_confidence: float
    is_handwritten: bool

# 1. Aadhaar Card
class AadhaarCard(BaseDocumentSchema):
    aadhaar_number: FieldExtraction
    full_name: FieldExtraction
    date_of_birth: FieldExtraction
    address: FieldExtraction

# 2. PAN Card
class PANCard(BaseDocumentSchema):
    pan_number: FieldExtraction
    full_name: FieldExtraction
    fathers_name: FieldExtraction
    date_of_birth: FieldExtraction

# 3. Driving Licence
class DrivingLicence(BaseDocumentSchema):
    dl_number: FieldExtraction
    name: FieldExtraction
    date_of_issue: FieldExtraction
    valid_till_date: FieldExtraction

# 4. Passport
class Passport(BaseDocumentSchema):
    passport_number: FieldExtraction
    date_of_birth: FieldExtraction
    date_of_expiry: FieldExtraction
    mrz_line_2: FieldExtraction

# 5. NACH / ECS Mandate
class NachEcsMandate(BaseDocumentSchema):
    bank_account_number: FieldExtraction
    ifsc_code: FieldExtraction
    bank_name: FieldExtraction
    amount_figures: FieldExtraction
    frequency: FieldExtraction

# 6. FATCA Annexure Form
class FatcaAnnexure(BaseDocumentSchema):
    policy_number: FieldExtraction
    tin_pan: FieldExtraction
    fathers_name: FieldExtraction
    place_of_birth: FieldExtraction
    nationality: FieldExtraction

# 7. Benefit Illustration Declaration
class BenefitIllustration(BaseDocumentSchema):
    application_number: FieldExtraction
    policyholder_name: FieldExtraction
    date: FieldExtraction
    place: FieldExtraction

# 8. Moral Hazard Questionnaire
class MoralHazardQuestionnaire(BaseDocumentSchema):
    application_number: FieldExtraction
    name_of_life_assured: FieldExtraction
    nominee_relationship: FieldExtraction
    date: FieldExtraction
    place: FieldExtraction

# 9. Multiple Policies Consent Form
class MultiplePoliciesConsent(BaseDocumentSchema):
    proposer_name: FieldExtraction
    reason_for_multiple_policies: FieldExtraction
    date: FieldExtraction
    place: FieldExtraction

# 10. Suitability Profiler Declaration
class SuitabilityProfiler(BaseDocumentSchema):
    application_number: FieldExtraction
    name_of_life_assured: FieldExtraction
    name_of_agent_sp: FieldExtraction
    date: FieldExtraction
    place: FieldExtraction

# 11. Assignment Request Form
class AssignmentRequestForm(BaseDocumentSchema):
    policy_number: FieldExtraction
    policyholder_name: FieldExtraction
    assignee_name: FieldExtraction
    reason_for_assignment: FieldExtraction
    date: FieldExtraction
    place: FieldExtraction

# 12. Proposal Form
class ProposalForm(BaseDocumentSchema):
    application_number: FieldExtraction
    name_of_life_assured: FieldExtraction
    insurance_plan_name: FieldExtraction
    premium_amount: FieldExtraction
    date: FieldExtraction
    place: FieldExtraction

# Flagging Report Schema
class FlaggedFieldRecord(BaseModel):
    document_filename: str
    document_type: str
    field_name: str
    extracted_value: str
    confidence_score: float
    threshold: float = 0.85
    extraction_method: str
    flagging_reason: str
    recommended_action: str

class FlaggingReport(BaseModel):
    confidence_threshold: float = 0.85
    threshold_rationale: str
    total_fields_extracted: int
    total_flagged_fields: int
    flagged_fields: List[FlaggedFieldRecord]
