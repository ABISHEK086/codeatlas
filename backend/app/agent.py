import json
import logging
import re
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm
from .config import settings
from .impact import analyze_impact
from .indexer import search_repo
from .models import File

log = logging.getLogger("codeatlas.agent")

MAX_TOOL_CHARS = 3500   # per tool result, keeps us inside free-tier token limits


# ---------------------------------------------------------------- schema
class Evidence(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None
    note: str = ""


class Finding(BaseModel):
    claim: str
    evidence: list[Evidence] = []


class Answer(BaseModel):
    summary: str
    findings: list[Finding] = []
    tests_to_run: list[str] = []
    checklist: list[str] = []
    confidence: Literal["low", "medium", "high"] = "medium"


# ---------------------------------------------------------------- tools
TOOLS = [
    {"type": "function", "function": {
        "name": "find_files",
        "description": "Find repository file paths containing a substring. Use this when unsure of an exact path.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string", "description": "e.g. 'models' or 'auth'"}},
            "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "get_impact",
        "description": "Change-impact report for one file: risk score with factors, direct and indirect "
                       "dependents, affected tests, affected API routes, co-changing files, recent commits.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "exact repo-relative file path"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "search_code",
        "description": "Semantic search over code chunks. Returns paths, line ranges and code.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "number of results, default 5, max 8"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read numbered lines of a file (max 150 lines per call).",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"}},
            "required": ["path"]}}},
]


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Toolbox:
    def __init__(self, db: Session, repo_id: int):
        self.db, self.repo_id = db, repo_id
        self._tools = {
            "find_files": self._find_files, "get_impact": self._get_impact,
            "search_code": self._search_code, "read_file": self._read_file,
        }

    def run(self, name: str, args: dict):
        fn = self._tools.get(name)
        if fn is None:
            return {"error": f"unknown tool '{name}'"}
        try:
            return fn(**args)
        except TypeError:
            return {"error": "invalid arguments"}
        except Exception as e:
            log.exception("tool %s failed", name)
            return {"error": str(e)[:200]}

    def _find_files(self, pattern: str):
        rows = self.db.scalars(
            select(File.path).where(File.repo_id == self.repo_id,
                                    File.path.ilike(f"%{pattern}%")).limit(20)).all()
        return rows or {"note": "no matching files"}

    def _get_impact(self, path: str):
        r = analyze_impact(self.db, self.repo_id, path)
        if r is None:
            return {"error": f"no file at '{path}'. Use find_files to get the exact path."}
        paths = lambda rows, n: [x["path"] for x in rows[:n]]  # noqa: E731
        return {
            "file": r["file"],
            "risk": r["risk"],
            "direct_dependents": paths(r["direct_dependents"], 20),
            "indirect_dependents": paths(r["indirect_dependents"], 15),
            "affected_tests": paths(r["affected_tests"], 15),
            "affected_routes": r["affected_routes"][:15],
            "depends_on": paths(r["depends_on"], 15),
            "co_change": r["co_change"][:6],
            "recent_commits": r["recent_commits"][:3],
            "history_commits_analysed": r["history_commits_analysed"],
        }

    def _search_code(self, query: str, k: int = 5):
        hits = search_repo(self.db, self.repo_id, query, min(max(_int(k, 5), 1), 8))
        if not hits:
            return {"note": "no results. The repo may not be indexed yet (POST /repos/{id}/index)."}
        return [{"path": h["path"], "start_line": h["start_line"], "end_line": h["end_line"],
                 "score": h["score"], "code": h["content"][:600]} for h in hits]

    def _read_file(self, path: str, start_line: int = 1, end_line: int | None = None):
        content = self.db.scalar(select(File.content).where(
            File.repo_id == self.repo_id, File.path == path))
        if content is None:
            return {"error": f"no file at '{path}'. Use find_files."}
        lines = content.splitlines()
        start = max(_int(start_line, 1), 1)
        end = min(_int(end_line, start + 99), start + 149, len(lines))
        return {"path": path, "start_line": start, "end_line": end, "total_lines": len(lines),
                "code": "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))}


# ---------------------------------------------------------------- prompts
SYSTEM = """You are CodeAtlas, an assistant that predicts the impact of code changes in one repository.

Rules:
- Context gathered by tools is provided in the user message. Call more tools if you need more facts.
- Never guess file paths: use find_files if unsure.
- Facts about dependents, tests, routes and history must come from tool results only.
- Do not invent a risk score. The engine computes it; explain it using the factors from get_impact.
- Only cite file paths and line numbers that appeared in tool results.
- If the tools do not give enough information, say so and lower your confidence.
- Be concise and specific."""

FINAL = """Now write the final answer. Respond with ONLY a JSON object in exactly this shape:
{
  "summary": "2-4 sentence answer to the question",
  "findings": [
    {"claim": "one specific statement",
     "evidence": [{"path": "repo/relative/path.py", "start_line": 12, "end_line": 20, "note": "why this supports the claim"}]}
  ],
  "tests_to_run": ["paths of affected tests, or an empty list"],
  "checklist": ["short, concrete steps to make the change safely"],
  "confidence": "low | medium | high"
}
Every finding needs at least one evidence item. Use null for start_line and end_line when the claim is
about a whole file (for example an import relationship). Only cite paths and lines seen in the tool results above."""


def _parse_answer(text: str) -> Answer:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return Answer.model_validate_json(text)


# ---------------------------------------------------------------- evidence check
def _verify(db: Session, repo_id: int, ev: Evidence) -> dict:
    path = ev.path.strip().removeprefix("./").lstrip("/")
    out = {"path": path, "start_line": ev.start_line, "end_line": ev.end_line,
           "note": ev.note, "verified": False, "snippet": None}
    content = db.scalar(select(File.content).where(File.repo_id == repo_id, File.path == path))
    if content is None:
        return out                                   # file does not exist: hallucinated
    if ev.start_line is None:
        out["verified"] = True                       # file-level evidence
        return out
    lines = content.splitlines()
    s, e = ev.start_line, ev.end_line or ev.start_line
    if 1 <= s <= e <= len(lines):
        out["verified"] = True
        out["snippet"] = "\n".join(lines[s - 1:min(e, s + 19)])
    return out


# ---------------------------------------------------------------- agent
def run_agent(db: Session, repo_id: int, question: str, file_path: str | None = None) -> dict:
    risk = None
    if file_path:
        impact = analyze_impact(db, repo_id, file_path)
        if impact is None:
            raise LookupError(f"No file at path '{file_path}'")
        risk = impact["risk"]

    user_msg = question
    if file_path:
        user_msg = f"I am planning to change `{file_path}`.\n{question}"

    tb = Toolbox(db, repo_id)
    trace: list[dict] = []
    gathered: list[str] = []

    # Seed context in code, so the model never starts empty-handed
    seeds: list[tuple[str, dict]] = []
    if file_path:
        seeds.append(("get_impact", {"path": file_path}))
    seeds.append(("search_code", {"query": question, "k": 5}))
    for name, args in seeds:
        result = json.dumps(tb.run(name, args), default=str)[:MAX_TOOL_CHARS]
        trace.append({"tool": name, "args": args})
        gathered.append(f"### {name}({json.dumps(args)})\n{result}")

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            user_msg + "\n\nContext already gathered:\n\n" + "\n\n".join(gathered))},
    ]

    # ---- phase 1: tool loop (the model may gather more) ----
    for step in range(settings.llm_max_steps):
        try:
            msg = llm.chat(messages, tools=TOOLS, tool_choice="auto")
        except llm.LLMError as e:
            if "tool_use_failed" in str(e):          # model produced a malformed tool call
                messages.append({"role": "user",
                                 "content": "Your last tool call was malformed. Retry with valid JSON arguments."})
                continue
            raise
        calls = msg.get("tool_calls")
        if not calls:
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}
            result = json.dumps(tb.run(name, args), default=str)[:MAX_TOOL_CHARS]
            trace.append({"tool": name, "args": args})
            gathered.append(f"### {name}({json.dumps(args)})\n{result}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    # ---- phase 2: structured answer, built from a flat digest of the tool results ----
    final_messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"Question: {user_msg}\n\nTool results gathered so far:\n\n"
            + "\n\n".join(gathered) + "\n\n" + FINAL)},
    ]
    answer: Answer | None = None
    for _ in range(2):
        raw = llm.chat(final_messages, json_mode=True, max_tokens=1800).get("content") or ""
        try:
            answer = _parse_answer(raw)
            break
        except ValueError as e:                      # pydantic ValidationError is a ValueError
            final_messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That JSON was invalid ({str(e)[:300]}). Return only the corrected JSON."},
            ]
    if answer is None:
        raise llm.LLMError("Model did not return valid JSON")

    # ---- verify every citation against the stored files ----
    findings = [{"claim": f.claim, "evidence": [_verify(db, repo_id, ev) for ev in f.evidence]}
                for f in answer.findings]
    all_ev = [ev for f in findings for ev in f["evidence"]]
    verified = sum(1 for ev in all_ev if ev["verified"])

    return {
        "question": question,
        "file": file_path,
        "risk": risk,                                # computed by code, not by the LLM
        "answer": {
            "summary": answer.summary,
            "findings": findings,
            "tests_to_run": answer.tests_to_run,
            "checklist": answer.checklist,
            "confidence": answer.confidence,
        },
        "grounding": {"evidence_total": len(all_ev), "evidence_verified": verified},
        "trace": trace,
        "model": settings.groq_model,
    }