from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class AuditorQueryRequest(BaseModel):
    query: str = Field(description="Auditor's natural language request")

class ApprovalRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None

class AuditStatusResponse(BaseModel):
    audit_id: str
    status: str
    proposed_controls: Optional[List[Dict[str, Any]]] = None
    message: str

class AuditReportResponse(BaseModel):
    audit_id: str
    query: str
    status: str
    controls_executed: Optional[List[Dict[str, Any]]] = None
    report: Optional[str] = None