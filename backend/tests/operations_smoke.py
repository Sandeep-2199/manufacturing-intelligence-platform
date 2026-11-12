"""Exercise shop-floor records, derived metrics, and access boundaries."""

from datetime import date

from team_smoke import browser, call, login


def main():
    editor, viewer, customer = (browser() for _ in range(3))
    login(editor, "testeditor")
    login(viewer, "testviewer")
    login(customer, "alpha-contact")
    today = date.today().isoformat()
    base = "/operations"
    snapshot = base + "/snapshot?as_of=" + today
    call(customer, "GET", snapshot, 403)
    call(customer, "GET", base + "/runs", 403)
    call(customer, "GET", base + "/quality", 403)
    machine = {"code": "CNC-01", "name": "Vertical machining center", "status": "running"}
    call(viewer, "POST", base + "/machines", 403, machine)
    saved = call(editor, "POST", base + "/machines", 201, machine)
    call(editor, "POST", base + "/machines", 409, machine)
    call(editor, "PUT", base + f"/machines/{saved['machine_id']}", data={**machine, "status": "maintenance"})

    stock = call(editor, "POST", base + "/stock", 201, {"sku": "AL-6061", "name": "Aluminum billets", "unit": "pieces", "reorder_point": 12})
    movements = base + f"/stock/{stock['item_id']}/movements"
    call(editor, "POST", movements, 201, {"delta": 20, "reason": "Receiving"})
    call(editor, "POST", movements, 201, {"delta": -10, "reason": "Issued to production"})
    call(editor, "POST", movements, 409, {"delta": -11, "reason": "Insufficient"})
    assert [m["delta"] for m in call(viewer, "GET", movements)] == [-10, 20]

    product = next(p for p in call(editor, "GET", "/products/") if p["is_active"])
    job = call(editor, "GET", snapshot)["jobs"][0]
    run = {"machine_id": saved["machine_id"], "product_id": product["product_id"], "job_id": job["job_id"],
           "production_date": today, "planned_minutes": 480, "run_minutes": 420,
           "ideal_cycle_seconds": 60, "units_produced": 360, "units_rejected": 12}
    call(editor, "POST", base + "/runs", 422, {**run, "units_rejected": 361})
    call(editor, "POST", base + "/runs", 404, {**run, "machine_id": 99999})
    recorded = call(editor, "POST", base + "/runs", 201, run)
    assert call(viewer, "GET", base + "/runs")[0]["job_reference"] == job["reference"]
    data = call(viewer, "GET", snapshot)
    assert data["stock"][0]["quantity"] == 10
    assert data["trend"] == [{"production_date": today, "output": 360, "rejected": 12, "planned": 480,
                              "runtime": 420, "ideal_seconds": 21600, "good_ideal_seconds": 20880}]

    inspection = {"run_id": recorded["run_id"], "inspected": 30, "rejected": 1, "notes": "Surface finish"}
    call(editor, "POST", base + "/quality", 422, {**inspection, "inspected": 361})
    call(editor, "POST", base + "/quality", 201, inspection)
    assert call(viewer, "GET", base + "/quality")[0]["rejected"] == 1
    print("Machine updates, stock ledger, production, inspection, and operations access checks passed.")


if __name__ == "__main__":
    main()
