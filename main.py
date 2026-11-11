import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from models import AuditorQueryRequest, ApprovalRequest, AuditStatusResponse, AuditReportResponse
from database import init_audit_db, save_pending_audit, get_audit, complete_audit, reject_audit
from investigation_agent import (
    reasoner_1_node,
    execute_data_tools_node,
    reasoner_2_node,
    execute_controls_node,
    final_report_node,
    AuditState
)
from langchain_core.messages import HumanMessage

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_audit_db()
    yield

app = FastAPI(title="Audit Compliance Workflow API", lifespan=lifespan)

@app.post("/audit/request", response_model=AuditStatusResponse)
async def submit_audit_request(req: AuditorQueryRequest):
    audit_id = f"aud_{uuid.uuid4().hex[:8]}"

    state: AuditState = {
        "messages": [HumanMessage(content=req.query)],
        "tools_parameter": [],
        "tools_output": [],
        "control_parameter": [],
        "control_output": []
    }

    r1_res = await reasoner_1_node(state)
    state["tools_parameter"] = r1_res["tools_parameter"]
    state["messages"].extend(r1_res["messages"])

    tool_res = await execute_data_tools_node(state)
    state["tools_output"] = tool_res["tools_output"]
    state["messages"].extend(tool_res["messages"])

    r2_res = await reasoner_2_node(state)
    state["control_parameter"] = r2_res["control_parameter"]
    state["messages"].extend(r2_res["messages"])

    save_pending_audit(audit_id, req.query, state)

    return AuditStatusResponse(
        audit_id=audit_id,
        status="PENDING_APPROVAL",
        proposed_controls=state["control_parameter"],
        message="Data retrieved and controls formulated. Awaiting Compliance Manager approval."
    )


@app.post("/audit/{audit_id}/approve", response_model=AuditStatusResponse)
async def process_approval(audit_id: str, req: ApprovalRequest):
    audit = get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit ticket not found")

    if audit["status"] != "PENDING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"Audit is already in status: {audit['status']}")

    if not req.approved:
        reject_audit(audit_id, req.rejection_reason or "No reason provided")
        return AuditStatusResponse(
            audit_id=audit_id,
            status="REJECTED",
            message="Audit execution was rejected."
        )

    state: AuditState = {
        "messages": [HumanMessage(content=audit["query"])],
        "tools_parameter": audit["tools_parameter"],
        "tools_output": audit["tools_output"],
        "control_parameter": audit["control_parameter"],
        "control_output": []
    }

    ctrl_res = await execute_controls_node(state)
    state["control_output"] = ctrl_res["control_output"]

    report_res = await final_report_node(state)
    final_report_text = report_res["messages"][-1].content

    complete_audit(audit_id, state["control_output"], final_report_text)

    return AuditStatusResponse(
        audit_id=audit_id,
        status="COMPLETED",
        proposed_controls=audit["control_parameter"],
        message="Controls executed and audit investigation report generated."
    )


@app.get("/audit/{audit_id}/report", response_model=AuditReportResponse)
def get_audit_report(audit_id: str):
    audit = get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit ticket not found")

    return AuditReportResponse(
        audit_id=audit["id"],
        query=audit["query"],
        status=audit["status"],
        controls_executed=audit.get("control_output"),
        report=audit.get("final_report")
    )