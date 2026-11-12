"""Add a week of sample activity for a local manufacturing walkthrough."""

import argparse
from datetime import date, timedelta

from sqlalchemy import text

from app.database import SessionLocal
from scripts.seed_demo import seed_demo


def seed_operations(username: str):
    with SessionLocal.begin() as db:
        actor = db.scalar(text("""
            SELECT user_id FROM team_users
            WHERE username = :username AND role = 'admin' AND is_active
        """), {"username": username})
        if actor is None:
            raise SystemExit("Create an active administrator before seeding sample activity.")
    seed_demo()
    today = date.today()
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(3814207604)"))
        db.execute(text("""
            INSERT INTO machines (code, name, status) VALUES
                ('DEMO-CNC-01', 'Vertical machining center', 'running'),
                ('DEMO-CNC-02', 'Turning center', 'running'),
                ('DEMO-QA-01', 'Inspection station', 'idle'),
                ('DEMO-CUT-01', 'Material cutting station', 'maintenance')
            ON CONFLICT (code) DO NOTHING
        """))
        db.execute(text("""
            WITH added AS (
                INSERT INTO stock_items (sku, name, unit, quantity, reorder_point) VALUES
                    ('DEMO-AL6061', 'Aluminum billets', 'pieces', 24, 30),
                    ('DEMO-ST4140', 'Steel blanks', 'pieces', 145, 60),
                    ('DEMO-PACK', 'Shipping cartons', 'pieces', 88, 20)
                ON CONFLICT (sku) DO NOTHING
                RETURNING item_id, quantity
            )
            INSERT INTO stock_movements (item_id, delta, reason, recorded_by)
            SELECT item_id, quantity, 'Opening demo balance', :actor FROM added
        """), {"actor": actor})
        db.execute(text("""
            INSERT INTO customer_companies (name) VALUES ('Demo Meridian Manufacturing')
            ON CONFLICT (name) DO NOTHING
        """))
        for ref, title, status, days in [
            ("DEMO-WO-101", "Mounting bracket batch", "in_progress", 2),
            ("DEMO-WO-102", "Drive shaft replenishment", "ready", 1),
            ("DEMO-WO-103", "Bearing spacer samples", "received", -1),
            ("DEMO-WO-104", "Pilot machining batch", "delivered", -2),
        ]:
            db.execute(text("""
                INSERT INTO customer_jobs (company_id, reference, title, status, expected_delivery)
                SELECT company_id, :ref, :title, :status, :delivery FROM customer_companies
                WHERE name = 'Demo Meridian Manufacturing'
                ON CONFLICT (company_id, reference) DO NOTHING
            """), {"ref": ref, "title": title, "status": status, "delivery": today + timedelta(days=days)})
        for days, output in enumerate([378, 310, 335, 265, 290, 220, 246]):
            run_id = db.scalar(text("""
                INSERT INTO production_runs (
                    machine_id, product_id, job_id, production_date, planned_minutes,
                    run_minutes, ideal_cycle_seconds, units_produced, units_rejected
                )
                SELECT m.machine_id, p.product_id, j.job_id, :run_date, 480, 420, 60, :output, :rejected
                FROM machines m CROSS JOIN products p
                CROSS JOIN customer_jobs j JOIN customer_companies c ON j.company_id = c.company_id
                WHERE m.code = 'DEMO-CNC-01' AND p.part_number = 'DEMO-BRK-100'
                    AND j.reference = 'DEMO-WO-101' AND c.name = 'Demo Meridian Manufacturing'
                    AND NOT EXISTS (
                        SELECT 1 FROM production_runs r WHERE r.machine_id = m.machine_id
                            AND r.job_id = j.job_id AND r.production_date = :run_date
                    )
                RETURNING run_id
            """), {"run_date": today - timedelta(days=days), "output": output, "rejected": days + 3})
            if run_id is not None and days == 0:
                db.execute(text("""
                    INSERT INTO quality_checks (run_id, inspected, rejected, notes, recorded_by)
                    VALUES (:run, 40, 1, 'Sample dimensional inspection', :actor)
                """), {"run": run_id, "actor": actor})
    print("Sample machines, inventory, work orders, and production activity are ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("administrator")
    seed_operations(parser.parse_args().administrator.lower())
