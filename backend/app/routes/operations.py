from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import TeamUser
from app.schemas.operations import InspectionWrite, MachineWrite, RunWrite, StockMovement, StockWrite
from app.services.security import current_user, require_team_access


router = APIRouter(prefix="/operations", tags=["Manufacturing operations"], dependencies=[Depends(require_team_access)])


def rows(db: Session, sql: str, **params):
    return [dict(row) for row in db.execute(text(sql), params).mappings()]


def save(db: Session, sql: str, **params):
    try:
        record = db.execute(text(sql), params).mappings().first()
        if record is None:
            raise HTTPException(status_code=404, detail="Record not found")
        result = dict(record)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        state = getattr(exc.orig, "sqlstate", None)
        if state == "23505":
            raise HTTPException(status_code=409, detail="This code is already in use") from exc
        if state == "23503":
            raise HTTPException(status_code=404, detail="Referenced record not found") from exc
        raise


@router.get("/snapshot")
def snapshot(as_of: date, db: Session = Depends(get_db)):
    return {
        "machines": rows(db, "SELECT * FROM machines ORDER BY code"),
        "stock": rows(db, "SELECT * FROM stock_items ORDER BY sku"),
        "jobs": rows(db, """
            SELECT j.job_id, j.company_id, j.reference, j.title, j.status, j.expected_delivery, c.name AS company
            FROM customer_jobs j JOIN customer_companies c USING (company_id)
            ORDER BY j.expected_delivery NULLS LAST, j.job_id DESC
        """),
        "trend": rows(db, """
            SELECT production_date, SUM(units_produced) AS output,
                SUM(units_rejected) AS rejected, SUM(planned_minutes) AS planned,
                SUM(run_minutes) AS runtime,
                SUM(units_produced::bigint * ideal_cycle_seconds) AS ideal_seconds,
                SUM((units_produced::bigint - units_rejected) * ideal_cycle_seconds) AS good_ideal_seconds
            FROM production_runs WHERE production_date BETWEEN :start_date AND :end_date
            GROUP BY production_date ORDER BY production_date
        """, start_date=as_of - timedelta(days=6), end_date=as_of),
    }


@router.post("/machines", status_code=201)
def create_machine(data: MachineWrite, db: Session = Depends(get_db)):
    return save(db, """
        INSERT INTO machines (code, name, status) VALUES (:code, :name, :status) RETURNING *
    """, **data.model_dump())


@router.put("/machines/{machine_id}")
def update_machine(machine_id: int, data: MachineWrite, db: Session = Depends(get_db)):
    return save(db, """
        UPDATE machines SET code = :code, name = :name, status = :status
        WHERE machine_id = :machine_id RETURNING *
    """, machine_id=machine_id, **data.model_dump())


@router.post("/stock", status_code=201)
def create_stock(data: StockWrite, db: Session = Depends(get_db)):
    return save(db, """
        INSERT INTO stock_items (sku, name, unit, reorder_point)
        VALUES (:sku, :name, :unit, :reorder_point) RETURNING *
    """, **data.model_dump())


@router.put("/stock/{item_id}")
def update_stock(item_id: int, data: StockWrite, db: Session = Depends(get_db)):
    return save(db, """
        UPDATE stock_items SET sku = :sku, name = :name, unit = :unit, reorder_point = :reorder_point
        WHERE item_id = :item_id RETURNING *
    """, item_id=item_id, **data.model_dump())


@router.get("/stock/{item_id}/movements")
def stock_history(item_id: int, db: Session = Depends(get_db)):
    return rows(db, """
        SELECT m.delta, m.reason, m.recorded_at, u.username
        FROM stock_movements m JOIN team_users u ON u.user_id = m.recorded_by
        WHERE m.item_id = :item_id ORDER BY m.movement_id DESC LIMIT 100
    """, item_id=item_id)


@router.post("/stock/{item_id}/movements", status_code=201)
def move_stock(item_id: int, data: StockMovement, user: TeamUser = Depends(current_user), db: Session = Depends(get_db)):
    quantity = db.scalar(text("SELECT quantity FROM stock_items WHERE item_id = :id FOR UPDATE"), {"id": item_id})
    if quantity is None:
        raise HTTPException(status_code=404, detail="Stock item not found")
    updated = quantity + data.delta
    if not 0 <= updated <= 2_147_483_647:
        raise HTTPException(status_code=409, detail="Adjustment would put stock outside the supported quantity range")
    db.execute(text("UPDATE stock_items SET quantity = :quantity WHERE item_id = :id"), {"quantity": updated, "id": item_id})
    return save(db, """
        INSERT INTO stock_movements (item_id, delta, reason, recorded_by)
        VALUES (:item_id, :delta, :reason, :user_id) RETURNING *
    """, item_id=item_id, user_id=user.user_id, **data.model_dump())


@router.get("/runs")
def list_runs(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    return rows(db, """
        SELECT r.*, m.code AS machine, p.part_number, p.product_name, j.reference AS job_reference
        FROM production_runs r JOIN machines m USING (machine_id) JOIN products p USING (product_id)
        LEFT JOIN customer_jobs j USING (job_id)
        ORDER BY r.production_date DESC, r.run_id DESC LIMIT :limit
    """, limit=limit)


@router.post("/runs", status_code=201)
def record_run(data: RunWrite, db: Session = Depends(get_db)):
    return save(db, """
        INSERT INTO production_runs (machine_id, product_id, job_id, production_date,
            planned_minutes, run_minutes, ideal_cycle_seconds, units_produced, units_rejected)
        VALUES (:machine_id, :product_id, :job_id, :production_date,
            :planned_minutes, :run_minutes, :ideal_cycle_seconds, :units_produced, :units_rejected)
        RETURNING *
    """, **data.model_dump())


@router.get("/quality")
def list_inspections(db: Session = Depends(get_db)):
    return rows(db, """
        SELECT q.*, p.part_number, m.code AS machine, u.username
        FROM quality_checks q JOIN production_runs r USING (run_id)
        JOIN products p USING (product_id) JOIN machines m USING (machine_id)
        JOIN team_users u ON u.user_id = q.recorded_by
        ORDER BY q.check_id DESC LIMIT 100
    """)


@router.post("/quality", status_code=201)
def record_inspection(data: InspectionWrite, user: TeamUser = Depends(current_user), db: Session = Depends(get_db)):
    output = db.scalar(text("SELECT units_produced FROM production_runs WHERE run_id = :id"), {"id": data.run_id})
    if output is None:
        raise HTTPException(status_code=404, detail="Production run not found")
    if data.inspected > output:
        raise HTTPException(status_code=422, detail="Inspected units cannot exceed the recorded run output")
    return save(db, """
        INSERT INTO quality_checks (run_id, inspected, rejected, notes, recorded_by)
        VALUES (:run_id, :inspected, :rejected, :notes, :user_id) RETURNING *
    """, user_id=user.user_id, **data.model_dump())
