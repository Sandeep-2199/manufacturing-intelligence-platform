"""Verify access, procedure retrieval, and production grounding without sending data externally."""

from datetime import date

from team_smoke import browser, call, login


def main():
    admin, viewer, customer = (browser() for _ in range(3))
    login(admin, "testadmin")
    login(viewer, "testviewer")
    login(customer, "alpha-contact")
    root = "/assistant"
    question = {"question": "How should we quarantine rejected brackets?"}
    procedure = {"title": "Inspection procedure", "content": "Quarantine rejected brackets in the red inspection bin. Record the batch reference."}
    call(customer, "POST", root + "/ask", 403, question)
    call(viewer, "POST", root + "/documents", 403, procedure)
    assert call(viewer, "POST", root + "/ask", data=question)["sources"] == []
    document = call(admin, "POST", root + "/documents", 201, procedure)
    assert call(admin, "GET", root + "/documents")[0]["title"] == procedure["title"]
    result = call(viewer, "POST", root + "/ask", data=question)
    assert result["answer"] is None and "OPENAI_API_KEY" in result["message"]
    assert "red inspection bin" in result["sources"][0]["content"]

    stock_question = {"question": "what are the current stocks in hand", "scope": "auto"}
    stock = call(viewer, "POST", root + "/ask", data=stock_question)
    assert stock["inventory"][0]["sku"] == "AL-6061"
    assert stock["inventory"][0]["quantity"] == 10
    assert stock["sources"][0]["title"].startswith("Current inventory balances")
    call(customer, "POST", root + "/ask", 403, stock_question)

    today = date.today().isoformat()
    both = call(viewer, "POST", root + "/ask", data={**question, "scope": "both", "start": today, "end": today})
    assert [source["id"] for source in both["sources"]] == ["S1", "S2"]
    assert '"rejected": 12' in both["sources"][1]["content"]
    run = call(viewer, "GET", "/operations/runs")[0]
    investigate = f"{root}/runs/{run['run_id']}/investigate"
    call(customer, "POST", investigate, 403)
    call(viewer, "POST", f"{root}/runs/99999/investigate", 404)
    report = call(viewer, "POST", investigate)
    assert report["findings"]["rejected"] == 12
    assert report["findings"]["reject_rate_pct"] == 3.33
    assert report["findings"]["prior_reject_rate_pct"] is None
    assert report["draft"] is None
    assert any("Surface finish" in source["content"] for source in report["sources"])
    assert any("red inspection bin" in source["content"] for source in report["sources"])

    call(admin, "DELETE", f"{root}/documents/{document['document_id']}", 204)
    assert call(viewer, "POST", root + "/ask", data=question)["sources"] == []
    print("Assistant staff access, retrieval, evidence, and deletion checks passed.")


if __name__ == "__main__":
    main()
