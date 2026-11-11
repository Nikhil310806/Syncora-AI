import asyncio
import json
import os
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict
from dotenv import load_dotenv

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

load_dotenv()

async def call_mcp(tool_name: str, args: dict) -> str:
  server_params = StdioServerParameters(
      command="python", args=["mcp_server.py"], env=dict(os.environ)
  )
  async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
      await session.initialize()
      res = await session.call_tool(tool_name, arguments=args)
      return res.content[0].text


class AuditState(TypedDict):
  messages: Annotated[Sequence[BaseMessage], add_messages]
  tools_parameter: List[Dict[str, Any]]
  tools_output: List[Dict[str, Any]]
  control_parameter: List[Dict[str, Any]]
  control_output: List[Dict[str, Any]]


class DataToolCall(BaseModel):
  table_name: str = Field(
      description="Table to retrieve from: 'commits' or 'pull_requests'"
  )
  owner: str = Field(description="Repository owner")
  repo: str = Field(description="Repository name")


class DataRetrievalSelection(BaseModel):
  tools: List[DataToolCall] = Field(
      description="List of data retrieval operations needed"
  )


class ControlItem(BaseModel):
  table_name: str = Field(
      description="Target table: 'commits' or 'pull_requests'"
  )
  owner: str = Field(description="Repository owner")
  repo: str = Field(description="Repository name")
  column_name: str = Field(
      description="Column to inspect (e.g. 'author_email', 'state')"
  )
  operator: str = Field(
      description="Operator: '=', '!=', '>', '<', '>=', '<=', 'LIKE', 'NOT"
      " LIKE'"
  )
  value: str = Field(
      description="Target value to test (e.g. '%@authorized.com', 'open')"
  )
  control_name: str = Field(
      description="Human-readable title for this audit control"
  )


class ControlSelection(BaseModel):
  controls: List[ControlItem] = Field(
      description="List of anomaly/compliance controls to execute"
  )

from llm_factory import get_llm

llm = get_llm(temperature=0.0)


async def reasoner_1_node(state: AuditState) -> Dict[str, Any]:
  structured_llm = llm.with_structured_output(DataRetrievalSelection)

  prompt = (
      "You are Reasoner 1. Analyze the auditor request and select which tables "
      "('commits' and/or 'pull_requests') need to be retrieved from the database."
  )

  messages = [SystemMessage(content=prompt)] + list(state["messages"])
  result: DataRetrievalSelection = await structured_llm.ainvoke(messages)

  params = [tool.model_dump() for tool in result.tools]
  return {
      "tools_parameter": params,
      "messages": [
          AIMessage(
              content=f"Reasoner 1 selected {len(params)} data retrieval"
              " tool(s)."
          )
      ],
  }

async def execute_data_tools_node(state: AuditState) -> Dict[str, Any]:
  outputs = []
  for param in state["tools_parameter"]:
    table = param["table_name"]
    args = {"owner": param["owner"], "repo": param["repo"]}

    if table == "commits":
      raw = await call_mcp("get_commits", args)
    elif table == "pull_requests":
      raw = await call_mcp("get_pull_requests", args)
    else:
      raw = json.dumps({"error": f"Invalid table {table}"})

    outputs.append({"table": table, "data": json.loads(raw)})

  return {
      "tools_output": outputs,
      "messages": [
          AIMessage(
              content=(
                  f"Executed data tools: Retrieved records for"
                  f" {[o['table'] for o in outputs]}."
              )
          )
      ],
  }


async def reasoner_2_node(state: AuditState) -> Dict[str, Any]:
  structured_llm = llm.with_structured_output(ControlSelection)

  prompt = f"""
You are Reasoner 2 (Compliance & Anomaly Controller).
Review the auditor request and the retrieved data records:

RETRIEVED DATA SUMMARY:
{json.dumps([{ 'table': item['table'], 'count': len(item['data']) } for item in state['tools_output']])}

Determine the audit controls to run. Specify:
- table_name ('commits' or 'pull_requests')
- column_name (e.g., 'author_email', 'state', 'committed_at')
- operator ('=', '!=', 'LIKE', 'NOT LIKE', '>', '<')
- value (filter value)
- control_name (e.g., 'Unauthorized Committer Check', 'Unmerged Open PR Check')
"""

  messages = [SystemMessage(content=prompt)] + list(state["messages"])
  result: ControlSelection = await structured_llm.ainvoke(messages)

  controls = [c.model_dump() for c in result.controls]
  return {
      "control_parameter": controls,
      "messages": [
          AIMessage(
              content=(
                  f"Reasoner 2 selected {len(controls)} audit control checks."
              )
          )
      ],
  }


async def execute_controls_node(state: AuditState) -> Dict[str, Any]:
  outputs = []
  for ctrl in state["control_parameter"]:
    table = ctrl["table_name"]
    args = {
        "owner": ctrl["owner"],
        "repo": ctrl["repo"],
        "column_name": ctrl["column_name"],
        "operator": ctrl["operator"],
        "value": ctrl["value"],
    }

    if table == "commits":
      raw = await call_mcp("query_commit_anomalies", args)
    elif table == "pull_requests":
      raw = await call_mcp("query_pr_anomalies", args)
    else:
      raw = json.dumps({"error": f"Invalid table {table}"})

    outputs.append({
        "control_name": ctrl["control_name"],
        "target_table": table,
        "criteria": f"{ctrl['column_name']} {ctrl['operator']} {ctrl['value']}",
        "flagged_records": json.loads(raw),
    })

  return {
      "control_output": outputs,
      "messages": [
          AIMessage(
              content=f"Executed {len(outputs)} audit controls via MCP."
          )
      ],
  }


async def final_report_node(state: AuditState) -> Dict[str, Any]:
  prompt = f"""
You are a Lead IT Security Auditor.
Synthesize the final audit report using the data and control outputs below:

CONTROLS EXECUTED & FLAGGED FINDINGS:
{json.dumps(state['control_output'], indent=2)}

Create an Executive Audit Report containing:
1. Scope & Execution Overview
2. Control Test Results (Passed / Failed)
3. Flagged Violations & Risk Level (Low/Medium/High)
4. Recommended Remediation
"""
  response = await llm.ainvoke([SystemMessage(content=prompt)])
  return {"messages": [response]}


workflow = StateGraph(AuditState)

workflow.add_node("reasoner_1", reasoner_1_node)
workflow.add_node("execute_data_tools", execute_data_tools_node)
workflow.add_node("reasoner_2", reasoner_2_node)
workflow.add_node("execute_controls", execute_controls_node)
workflow.add_node("final_report", final_report_node)

workflow.set_entry_point("reasoner_1")
workflow.add_edge("reasoner_1", "execute_data_tools")
workflow.add_edge("execute_data_tools", "reasoner_2")
workflow.add_edge("reasoner_2", "execute_controls")
workflow.add_edge("execute_controls", "final_report")
workflow.add_edge("final_report", END)

audit_app = workflow.compile()


async def main():
  query = (
      "Audit repo 'Hello-World' owned by 'octocat'. "
      "Check for unauthorized commits not using '@company.com' email, "
      "and detect open pull requests."
  )

  initial_state = {
      "messages": [HumanMessage(content=query)],
      "tools_parameter": [],
      "tools_output": [],
      "control_parameter": [],
      "control_output": [],
  }

  print(f"\n[*] Starting Audit: {query}\n" + "-" * 60)

  async for event in audit_app.astream(initial_state):
    for node, updates in event.items():
      print(f"\n[Completed Step: {node}]")
      if "tools_parameter" in updates:
        print(f" -> Tools Selected: {updates['tools_parameter']}")
      if "tools_output" in updates:
        print(
            " -> Records Fetched:"
            f" {[(x['table'], len(x['data'])) for x in updates['tools_output']]}"
        )
      if "control_parameter" in updates:
        print(
            " -> Controls Formulated:"
            f" {[c['control_name'] for c in updates['control_parameter']]}"
        )
      if "control_output" in updates:
        print(
            " -> Control Findings:"
            f" {[(c['control_name'], len(c['flagged_records'])) for c in updates['control_output']]}"
        )
      if node == "final_report":
        print("\n" + "=" * 60)
        print("FINAL AUDIT INVESTIGATION REPORT")
        print("=" * 60)
        print(updates["messages"][-1].content)


if __name__ == "__main__":
  asyncio.run(main())