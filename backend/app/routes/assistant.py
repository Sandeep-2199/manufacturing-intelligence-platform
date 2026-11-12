import json
import os
import re
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, StringConstraints, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.assistant import generate_answer, production_evidence, retrieve_passages, split_passages
from app.services.security import require_admin, require_staff


router = APIRouter(prefix="/assistant", tags=["Manufacturing assistant"], dependencies=[Depends(require_staff)])


class DocumentWrite(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=60000)]


class Question(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1200)]
    scope: Literal["auto", "procedures", "production", "both", "inventory"] = "procedures"
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.search_scope in {"production", "both"}:
            if not self.start or not self.end or not timedelta(0) <= self.end - self.start <= timedelta(days=30):
                raise ValueError("Choose a production period of 1 to 31 days.")
        return self


    @property
    def search_scope(self) -> str:
        if self.scope != "auto":
            return self.scope
        if re.search(r"\b(?:stocks?|inventory|on hand|in hand|reorder)\b", self.question, re.IGNORECASE):
            return "inventory"
        if re.search(r"\b(?:how many|total|most|count|rate)\b.*\b(?:reject\w*|production|output|units)\b", self.question, re.IGNORECASE):
            return "production"
        return "procedures"


@router.get("/documents", dependencies=[Depends(require_admin)])
def list_documents(db: Session = Depends(get_db)):
    return [dict(row) for row in db.execute(text(
        "SELECT document_id, title, added_at FROM knowledge_documents ORDER BY title"
    )).mappings()]


@router.post("/documents", status_code=201, dependencies=[Depends(require_admin)])
def add_document(data: DocumentWrite, db: Session = Depends(get_db)):
    document_id = db.scalar(text("""
        INSERT INTO knowledge_documents (title) VALUES (:title)
        ON CONFLICT (title) DO NOTHING RETURNING document_id
    """), {"title": data.title})
    if document_id is None:
        raise HTTPException(409, "A procedure with this title already exists.")
    db.execute(text("""
        INSERT INTO knowledge_passages (document_id, passage_number, content)
        VALUES (:document_id, :passage_number, :content)
    """), [
        {"document_id": document_id, "passage_number": number, "content": passage}
        for number, passage in enumerate(split_passages(data.content), 1)
    ])
    db.commit()
    return {"document_id": document_id, "title": data.title}


@router.delete("/documents/{document_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_document(document_id: int, db: Session = Depends(get_db)):
    removed = db.scalar(text("""
        DELETE FROM knowledge_documents WHERE document_id = :id RETURNING document_id
    """), {"id": document_id})
    if removed is None:
        raise HTTPException(404, "Procedure not found.")
    db.commit()
    return Response(status_code=204)


@router.post("/ask")
def ask(data: Question, db: Session = Depends(get_db)):
    sources = []
    scope = data.search_scope
    stock = []
    if scope == "inventory":
        stock = [dict(row) for row in db.execute(text("""
            SELECT sku, name, quantity, unit, reorder_point FROM stock_items ORDER BY sku LIMIT 51
        """)).mappings()]
        sources.append({
            "id": "S1", "title": "Current inventory balances (up to 50 items)",
            "content": json.dumps({
                "items": stock[:50],
                "has_more_items": len(stock) > 50,
                "query_result": "Inventory items found." if stock else "No inventory items are recorded.",
            }, indent=2),
        })
    if scope in {"procedures", "both"}:
        for passage in retrieve_passages(db, data.question):
            sources.append({
                "id": f"S{len(sources) + 1}", "title": f"{passage['title']} · Passage {passage['passage']}",
                "content": passage["content"],
            })
    if scope in {"production", "both"}:
        production = production_evidence(db, data.start, data.end)
        if production:
            sources.append({
                "id": f"S{len(sources) + 1}", "title": f"PostgreSQL production records · {data.start} to {data.end}",
                "content": json.dumps(production, default=str),
            })
    db.rollback()  # Release the database transaction before waiting on the model.
    result = {"answer": None, "message": None, "sources": sources, "scope": scope, "inventory": stock[:50],
              "inventory_truncated": len(stock) > 50}
    if not sources:
        message = {
            "procedures": "No saved work instructions match this question. Add an approved instruction or try different words.",
            "production": "No production runs are recorded for those dates. Choose a period with runs.",
            "both": "No work instructions matched, and no production runs were recorded for those dates.",
        }[scope]
        return {**result, "message": message}
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {**result, "message": "Evidence retrieved. Configure OPENAI_API_KEY to generate an answer."}
    try:
        return {**result, "answer": generate_answer(data.question, sources, api_key)}
    except HTTPException as error:
        if error.status_code != 502:
            raise
        return {**result, "message": error.detail}


@router.post("/runs/{run_id}/investigate")
def investigate_run(run_id: int, db: Session = Depends(get_db)):
    run = db.execute(text("""
        SELECT r.run_id, r.machine_id, r.product_id, r.production_date, r.units_produced,
               r.units_rejected, m.code AS machine, p.part_number, j.reference AS work_order
        FROM production_runs r JOIN machines m USING (machine_id) JOIN products p USING (product_id)
        LEFT JOIN customer_jobs j USING (job_id)
        WHERE r.run_id = :id
    """), {"id": run_id}).mappings().first()
    if run is None:
        raise HTTPException(404, "Production run not found.")
    previous = db.execute(text("""
        SELECT COUNT(*) AS runs, COALESCE(SUM(units_produced), 0) AS produced,
               COALESCE(SUM(units_rejected), 0) AS rejected
        FROM (
            SELECT units_produced, units_rejected FROM production_runs
            WHERE machine_id = :machine_id AND product_id = :product_id AND units_produced > 0
              AND (production_date, run_id) < (:production_date, :run_id)
            ORDER BY production_date DESC, run_id DESC LIMIT 10
        ) AS prior_runs
    """), dict(run)).mappings().one()
    checks = db.execute(text("""
        SELECT check_id, inspected, rejected, notes FROM quality_checks
        WHERE run_id = :id ORDER BY check_id DESC LIMIT 5
    """), {"id": run_id}).mappings()
    inspections = [dict(check) for check in checks]
    passages = retrieve_passages(
        db, f"{run['machine']} {run['part_number']} rejected nonconforming parts quality inspection"
    )
    current_rate = round(100 * run["units_rejected"] / run["units_produced"], 2) if run["units_produced"] else None
    baseline_rate = round(100 * previous["rejected"] / previous["produced"], 2) if previous["produced"] else None
    findings = {
        "rejected": run["units_rejected"], "produced": run["units_produced"],
        "reject_rate_pct": current_rate, "prior_runs": previous["runs"],
        "prior_reject_rate_pct": baseline_rate, "procedure_matches": len(passages),
    }
    sources = [
        {"id": "S1", "title": f"Production run #{run_id}",
         "content": json.dumps(dict(run), default=str, indent=2)},
        {"id": "S2", "title": "Previous runs for the same machine and part",
         "content": json.dumps({**dict(previous), "reject_rate_pct": baseline_rate}, indent=2)},
    ]
    if inspections:
        sources.append({"id": "S3", "title": "Latest inspection records for this run",
                        "content": json.dumps(inspections, indent=2)})
    for passage in passages:
        sources.append({
            "id": f"S{len(sources) + 1}", "title": f"{passage['title']} · Passage {passage['passage']}",
            "content": passage["content"],
        })
    db.rollback()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"findings": findings, "sources": sources, "draft": None,
                "message": "Evidence is ready. Configure OPENAI_API_KEY to generate the handoff draft."}
    prompt = (
        "Draft a quality handoff for a supervisor. Include observed facts, comparison with prior runs, "
        "what the records cannot establish, and what a reviewer should verify next. Cite the evidence. "
        "Use a procedure for recommended steps only if it applies to this case. Explicitly say when "
        "there is no applicable procedure or historical baseline. Do not infer a root cause, "
        "decide disposition, approve a release, or claim that a corrective action was taken."
    )
    try:
        draft = generate_answer(prompt, sources, api_key)
    except HTTPException as error:
        if error.status_code != 502:
            raise
        return {"findings": findings, "sources": sources, "draft": None, "message": error.detail}
    return {"findings": findings, "sources": sources, "draft": draft, "message": None}
