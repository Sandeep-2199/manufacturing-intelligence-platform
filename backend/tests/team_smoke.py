"""Exercise the team workspace over HTTP against the disposable database."""

import json
import sys
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


PASSWORD = "Test123!"


def browser():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def call(client, method, path, status=200, data=None, headers=None):
    request = Request(
        f"{sys.argv[1]}{path}",
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        response = client.open(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        assert response.status == status, (method, path, response.status, body)
        assert response.headers.get("Cache-Control") == "no-store"
        if path == "/auth/login" and status == 200:
            cookie = response.headers["Set-Cookie"].lower()
            assert "httponly" in cookie and "samesite=strict" in cookie
    return json.loads(body) if body else None


def login(client, username, status=200, password=PASSWORD):
    return call(client, "POST", "/auth/login", status, {"username": username, "password": password})


def main():
    admin, viewer, editor, anonymous = (browser() for _ in range(4))
    call(anonymous, "GET", "/products/", 401)
    call(anonymous, "GET", "/vendors/", 401)
    call(anonymous, "GET", "/products/1/suppliers", 401)
    call(anonymous, "GET", "/team/users", 401)
    invalid = login(anonymous, "testadmin", 422, password="short")
    assert "short" not in json.dumps(invalid)
    login(anonymous, "testadmin", 401, password="Wrong test password")
    assert login(admin, "TESTADMIN")["role"] == "admin"
    users = call(admin, "GET", "/team/users")
    assert len(users) == 1 and "password_hash" not in users[0]

    for role in ("viewer", "editor"):
        payload = {"username": f"test{role}", "password": PASSWORD, "role": role}
        assert call(admin, "POST", "/team/users", 201, payload)["role"] == role
        call(admin, "POST", "/team/users", 409, payload)

    assert login(viewer, "testviewer")["role"] == "viewer"
    assert len(call(viewer, "GET", "/products/")) == 3
    call(viewer, "POST", "/products/", 403, {"part_number": "TEST-01", "product_name": "Forbidden"})
    call(viewer, "POST", "/vendors/1/products/1", 403)
    call(viewer, "GET", "/team/users", 403)

    assert login(editor, "testeditor")["role"] == "editor"
    call(editor, "POST", "/team/users", 403, {"username": "forbidden", "password": PASSWORD})
    call(editor, "POST", "/products/", 403, {"part_number": "TEST-01", "product_name": "Blocked"},
         headers={"Origin": "https://other.example"})
    call(editor, "POST", "/products/", 403, {"part_number": "TEST-01", "product_name": "Blocked"},
         headers={"Sec-Fetch-Site": "same-site"})

    product = call(editor, "POST", "/products/", 201, {"part_number": "TEST-01", "product_name": "Test bracket"})
    product_path = f"/products/{product['product_id']}"
    call(editor, "PUT", product_path, data={"part_number": "TEST-01", "product_name": "Test bracket v2"})
    vendor = call(editor, "POST", "/vendors/", 201, {"vendor_code": "TEST-V", "vendor_name": "Test supplier"})
    vendor_path = f"/vendors/{vendor['vendor_id']}"
    vendor = call(editor, "PUT", vendor_path, data={"vendor_code": "TEST-V", "vendor_name": "Test Metals"})
    link = vendor_path + product_path
    terms = {"unit_price": "8.40", "lead_time_days": 5}
    assert call(editor, "POST", link, 201, terms)["unit_price"] == "8.40"
    call(editor, "POST", link, 409, terms)
    call(editor, "PUT", link, 422, {"unit_price": "-1.00"})
    changed = {"unit_price": "7.25", "lead_time_days": 3}
    assert call(editor, "PUT", link, data=changed)["lead_time_days"] == 3
    comparison = call(viewer, "GET", product_path + "/suppliers")
    assert comparison["suppliers"] == [{**changed, "vendor": vendor}]
    assert call(viewer, "GET", vendor_path + "/products")[0]["product_id"] == product["product_id"]
    call(editor, "DELETE", link, 204)
    call(editor, "DELETE", link, 404)
    assert call(viewer, "GET", product_path + "/suppliers")["suppliers"] == []
    call(editor, "DELETE", product_path, 204)
    assert not call(viewer, "GET", product_path)["is_active"]

    call(editor, "POST", "/auth/logout", 204)
    call(editor, "GET", "/auth/me", 401)
    for _ in range(8):
        login(anonymous, "testadmin", 401, password="Wrong test password")
    login(anonymous, "testadmin", 429)
    print("Team roles, origin checks, rate limit, and full sourcing workflow passed.")


if __name__ == "__main__":
    main()
