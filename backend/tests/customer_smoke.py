"""Verify the customer workflow and company boundaries over HTTP."""

from team_smoke import PASSWORD, browser, call, login


def main():
    admin, editor, viewer, first, second, anonymous = (browser() for _ in range(6))
    login(admin, "testadmin")
    login(editor, "testeditor")
    login(viewer, "testviewer")

    call(anonymous, "GET", "/portal/jobs", 401)
    call(admin, "GET", "/portal/jobs", 403)
    call(viewer, "POST", "/work/companies", 403, {"name": "Denied Company"})

    alpha = call(editor, "POST", "/work/companies", 201, {"name": "Alpha Fabrication"})
    beta = call(admin, "POST", "/work/companies", 201, {"name": "Beta Engineering"})
    paths = [f"/work/companies/{company['company_id']}" for company in (alpha, beta)]
    call(editor, "POST", paths[0] + "/invitations", 403, {"username": "denied-contact"})
    call(viewer, "GET", paths[0] + "/jobs")
    job = {"reference": "PO-100", "title": "Bracket batch", "expected_delivery": "2027-01-20"}
    alpha_job = call(editor, "POST", paths[0] + "/jobs", 201, job)
    beta_job = call(editor, "POST", paths[1] + "/jobs", 201, {**job, "title": "Shaft batch"})
    call(editor, "POST", paths[0] + "/jobs", 409, job)
    call(editor, "PUT", paths[1] + f"/jobs/{alpha_job['job_id']}", 404, job)
    alpha_job = call(editor, "PUT", paths[0] + f"/jobs/{alpha_job['job_id']}", data={
        **job, "status": "in_progress",
    })

    for client, username, path in zip((first, second), ("alpha-contact", "beta-contact"), paths):
        invitation = call(admin, "POST", path + "/invitations", 201, {"username": username})
        data = {"token": invitation["token"], "password": PASSWORD}
        account = call(client, "POST", "/portal/invitations/accept", 201, data)
        assert account["username"] == username and account["role"] == "customer"
        call(client, "POST", "/portal/invitations/accept", 404, data)
        assert login(client, username)["role"] == "customer"

    for client, company, own, other in (
        (first, alpha, alpha_job, beta_job),
        (second, beta, beta_job, alpha_job),
    ):
        assert call(client, "GET", "/portal/company") == company
        assert call(client, "GET", "/portal/jobs") == [own]
        assert call(client, "GET", f"/portal/jobs/{own['job_id']}") == own
        call(client, "GET", f"/portal/jobs/{other['job_id']}", 404)
        for path in ("/products/", "/vendors/", "/products/1/suppliers", "/team/users", "/work/companies", *[p + "/jobs" for p in paths]):
            call(client, "GET", path, 403)
        call(client, "PUT", paths[0] + f"/jobs/{alpha_job['job_id']}", 403, job)

    call(first, "POST", "/auth/logout", 204)
    call(first, "GET", "/portal/jobs", 401)
    print("Customer invitations, job updates, and two-company access boundaries passed.")


if __name__ == "__main__":
    main()
