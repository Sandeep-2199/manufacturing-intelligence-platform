#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
pg_bin="${PG_BIN:-$(pg_config --bindir)}"
python_bin="${MIP_TEST_PYTHON:-venv/bin/python}"
port="${MIP_TEST_PORT:-8014}"
test_dir=$(mktemp -d /tmp/mip-team.XXXXXX)
api_pid=
cleanup() {
    if [[ -n "$api_pid" ]]; then
        kill "$api_pid" 2>/dev/null || true
        wait "$api_pid" 2>/dev/null || true
    fi
    "$pg_bin/pg_ctl" -D "$test_dir/pg" -m fast stop >/dev/null 2>&1 || true
    rm -rf "$test_dir"
}
trap cleanup EXIT

"$pg_bin/initdb" -D "$test_dir/pg" -U mip_test -A trust --no-locale --encoding=UTF8 >"$test_dir/init.log"
"$pg_bin/pg_ctl" -D "$test_dir/pg" -l "$test_dir/pg.log" \
    -o "-k $test_dir -p 55432 -c listen_addresses=" -w start
export PGHOST="$test_dir" PGPORT=55432 PGUSER=mip_test PGDATABASE=postgres
export DATABASE_URL="postgresql+psycopg://mip_test@/postgres?host=$test_dir&port=55432"
export OPENAI_API_KEY=""
export MIP_SECURE_COOKIE=false MIP_ORIGIN="http://127.0.0.1:$port"

# Simulate the old app's unversioned catalog and verify the migration preserves it.
"$python_bin" - <<'PY'
from app.database import Base, engine
from scripts.seed_demo import seed_demo

Base.metadata.create_all(engine)
seed_demo()
PY
"$python_bin" -m scripts.migrate
"$python_bin" -m scripts.migrate
"$python_bin" -m scripts.seed_demo
"$python_bin" - <<'PY'
import sys
from scripts import manage_account

sys.argv = ["manage_account", "create-admin", "testadmin"]
manage_account.getpass = lambda _: "Local test password 42!"
manage_account.main()
PY

"$python_bin" -m uvicorn app.main:app --host 127.0.0.1 --port "$port" >"$test_dir/api.log" 2>&1 &
api_pid=$!
ready=false
for attempt in {1..30}; do
    if kill -0 "$api_pid" 2>/dev/null && curl -fsS "http://127.0.0.1:$port/health/db" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 0.2
done
if [[ "$ready" != true ]]; then
    cat "$test_dir/api.log"
    exit 1
fi
curl -fsS "http://127.0.0.1:$port/dashboard/" >"$test_dir/index.html"
grep -q 'Team sign-in' "$test_dir/index.html"
"$python_bin" tests/team_smoke.py "http://127.0.0.1:$port"
"$pg_bin/psql" -c 'TRUNCATE login_attempts'
curl -fsS "http://127.0.0.1:$port/customer/sign-in" >"$test_dir/customer.html"
grep -q 'Customer sign-in' "$test_dir/customer.html"
"$python_bin" tests/customer_smoke.py "http://127.0.0.1:$port"
"$python_bin" tests/operations_smoke.py "http://127.0.0.1:$port"
"$python_bin" tests/assistant_smoke.py "http://127.0.0.1:$port"

"$pg_bin/pg_dump" -Fc -f "$test_dir/team.dump"
"$pg_bin/createdb" mip_restore
"$pg_bin/pg_restore" -d mip_restore --exit-on-error "$test_dir/team.dump"
"$pg_bin/psql" -d mip_restore -v ON_ERROR_STOP=1 -c 'TRUNCATE team_sessions, login_attempts, customer_invitations'
"$pg_bin/psql" -d mip_restore -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
    IF (SELECT count(*) FROM schema_migrations) <> 5
        OR (SELECT count(*) FROM products) <> 4
        OR (SELECT count(*) FROM vendor_products) <> 5
        OR (SELECT count(*) FROM team_users) <> 5
        OR (SELECT count(*) FROM customer_jobs) <> 2
        OR (SELECT count(*) FROM production_runs) <> 1
        OR (SELECT quantity FROM stock_items WHERE sku = 'AL-6061') IS DISTINCT FROM 10
        OR (SELECT count(*) FROM team_sessions) <> 0 THEN
        RAISE EXCEPTION 'Unexpected data in restored database';
    END IF;
END
$$;
SQL
echo 'Existing catalog migration, repeatable seed, and backup restore passed.'

"$pg_bin/createdb" mip_fresh
DATABASE_URL="postgresql+psycopg://mip_test@/mip_fresh?host=$test_dir&port=55432" \
    "$python_bin" -m scripts.migrate
echo 'Fresh database migration passed.'

"$python_bin" -m scripts.seed_operations testadmin
"$python_bin" -m scripts.seed_operations testadmin
"$pg_bin/psql" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
    IF (SELECT count(*) FROM production_runs) <> 8
        OR (SELECT count(*) FROM stock_movements) <> 5
        OR (SELECT count(*) FROM customer_jobs) <> 6 THEN
        RAISE EXCEPTION 'Demo activity was incomplete or duplicated';
    END IF;
END
$$;
SQL
echo 'Repeatable manufacturing demo seed passed.'

if [[ "${1:-}" == "--hold" ]]; then
    "$pg_bin/psql" -c 'TRUNCATE login_attempts'
    echo "Disposable preview at http://127.0.0.1:$port/dashboard/"
    read -r _
fi
