import json
import sqlite3
from typing import Any, Dict, List
from mcp.server.fastmcp import FastMCP

DB_FILE = "github_data.db"
mcp = FastMCP("github-audit-mcp")

ALLOWED_OPERATORS = ["=", "!=", ">", "<", ">=", "<=", "LIKE", "NOT LIKE"]
COMMITS_COLS = {
    "sha",
    "owner",
    "repo",
    "author_name",
    "author_email",
    "message",
    "committed_at",
}
PRS_COLS = {
    "id",
    "owner",
    "repo",
    "number",
    "title",
    "state",
    "author_login",
    "created_at",
}


def query_db(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
  with sqlite3.connect(DB_FILE) as conn:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    rows = cursor.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


@mcp.tool()
def get_commits(owner: str, repo: str, limit: int = 50) -> str:
  """Fetch saved commits for a given owner and repository."""
  sql = (
      "SELECT * FROM commits WHERE owner = ? AND repo = ? ORDER BY"
      " committed_at DESC LIMIT ?"
  )
  results = query_db(sql, (owner, repo, limit))
  return json.dumps(results)


@mcp.tool()
def get_pull_requests(owner: str, repo: str, limit: int = 50) -> str:
  """Fetch saved pull requests for a given owner and repository."""
  sql = (
      "SELECT * FROM pull_requests WHERE owner = ? AND repo = ? ORDER BY"
      " created_at DESC LIMIT ?"
  )
  results = query_db(sql, (owner, repo, limit))
  return json.dumps(results)


@mcp.tool()
def query_commit_anomalies(
    owner: str, repo: str, column_name: str, operator: str, value: str
) -> str:
  """Filter commits by a specific anomaly condition.

  Example: column_name='author_email', operator='NOT LIKE',
  value='%@company.com'
  """
  if column_name not in COMMITS_COLS:
    return json.dumps({"error": f"Invalid column '{column_name}' for commits"})
  op_clean = operator.strip().upper()
  if op_clean not in ALLOWED_OPERATORS:
    return json.dumps({"error": f"Invalid operator '{operator}'"})

  sql = (
      f"SELECT * FROM commits WHERE owner = ? AND repo = ? AND {column_name}"
      f" {op_clean} ?"
  )
  results = query_db(sql, (owner, repo, value))
  return json.dumps(results)


@mcp.tool()
def query_pr_anomalies(
    owner: str, repo: str, column_name: str, operator: str, value: str
) -> str:
  """Filter pull requests by a specific anomaly condition.

  Example: column_name='state', operator='=', value='open'
  """
  if column_name not in PRS_COLS:
    return json.dumps(
        {"error": f"Invalid column '{column_name}' for pull_requests"}
    )
  op_clean = operator.strip().upper()
  if op_clean not in ALLOWED_OPERATORS:
    return json.dumps({"error": f"Invalid operator '{operator}'"})

  sql = (
      f"SELECT * FROM pull_requests WHERE owner = ? AND repo = ? AND"
      f" {column_name} {op_clean} ?"
  )
  results = query_db(sql, (owner, repo, value))
  return json.dumps(results)


if __name__ == "__main__":
  mcp.run()