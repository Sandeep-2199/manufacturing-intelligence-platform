# Manufacturing Intelligence Platform

A team sourcing workspace built with FastAPI, PostgreSQL, and a browser dashboard.

## Start locally

Use the existing PostgreSQL database, or create a development database and set `DATABASE_URL` in `backend/.env`. The URL format is `postgresql+psycopg://USER:PASSWORD@localhost:5432/DATABASE`.

From the repository root:

```bash
cd backend
source venv/bin/activate
python -m scripts.migrate
python -m scripts.manage_account create-admin teamadmin
python -m scripts.seed_demo  # Optional sample data
python -m uvicorn app.main:app --reload
```

Create the administrator once. The command prompts for a password of at least 8 characters. For a fresh checkout, first create a virtual environment with `python3 -m venv venv`, activate it, and install `requirements.txt` from `backend`.

Open [the dashboard](http://127.0.0.1:8000/dashboard/) and sign in. [API docs](http://127.0.0.1:8000/docs) can use the same browser session.

| Role | Access |
|---|---|
| Viewer | Browse products and compare supplier offers |
| Editor | Viewer access plus create and edit products and vendors, deactivate products, and link, edit, or unlink offers |
| Administrator | Editor access plus list and create team accounts |

Use **Team accounts** to add an editor or viewer. Use `python -m scripts.manage_account reset-password USERNAME` to reset a password or `python -m scripts.manage_account disable USERNAME` to disable access. Both commands revoke the account's existing sessions. Use the same commands with `docker compose exec app python -m ...` on the host.

The seed creates three products and five sourcing links. It can be rerun without overwriting existing values for the reserved `DEMO-` codes. Start with **Mounting Bracket**, then sort by **Lead time** to see how the fastest offer differs from the lowest-priced offer.

## Manufacturing workspace

Open the team dashboard after applying migrations. For a populated local walkthrough, run this from `backend` using your administrator username.

```bash
python -m scripts.seed_operations teamadmin
```

The command adds sample catalog records, machines, stock movements, work orders and seven days of production without replacing existing values. Use a demo database for this exercise.

1. **Machines** records the current machine status.
2. **Inventory** records receipts and usage as signed movements. A movement records the operator and reason. The balance and history are saved together.
3. **Work orders** manages customer companies, job status, delivery dates and portal invitations.
4. **Production** records runs against a machine and product, with an optional work order. Export the displayed run history to CSV.
5. **Quality control** records sample inspection counts and notes against a run.
6. **Overview** reads those records for production totals, trends, work orders and alerts. Equipment effectiveness divides the ideal production time for good units by planned time. The breakdown shows availability, performance and quality. Inspection samples are tracked separately from run reject totals.

Machine statuses, quantities and job updates are entered by staff. The overview updates on refresh.

## Customer portal

Run `python -m scripts.migrate` from `backend` to add the customer tables. Then start or restart Uvicorn.

1. Sign in to the team dashboard as an administrator. Select **Customer jobs**, then **Add company**.
2. Open that company and select **Add job**. Enter a customer-facing job reference, title, status, and optional expected delivery date. Editors can update jobs as work progresses.
3. Select **Create invitation** and choose a username for the contact. Copy the link and send it directly to that person. The link is valid for 24 hours and works once. Links made on localhost can be opened on your machine. Generate customer links on the team's HTTPS domain when the app is deployed.
4. Open the invitation in a private browser window to practice. Set a password, then sign in with the username shown. The portal displays jobs for the company tied to that account.

Customer accounts can only view their company's jobs. The API looks up the company from the signed-in account and applies it to every job query. Use `python -m scripts.manage_account disable USERNAME` to revoke an account, including its current sessions. After restoring a backup, send fresh invitations for any contacts who had not activated their accounts.

## Deploy a portfolio demo on Render

1. Push the repository to GitHub. In Render, choose **New → Blueprint**, connect that repository, and select the branch containing `render.yaml`.
2. Enter a unique 8–128 character password for `MIP_BOOTSTRAP_ADMIN_PASSWORD` in the Render setup prompt. The first start applies the migrations and creates `teamadmin`. Later starts leave existing administrators alone. Remove the bootstrap variable from the service environment after signing in successfully.
3. Once the service is live, open its Render URL followed by `/dashboard/` and sign in as `teamadmin`. For a public portfolio walkthrough, create a viewer account with a separate password.
4. Optionally set `OPENAI_API_KEY` in the Render service's **Environment** settings to enable generation. Use a key with available API quota. Use synthetic records for public demos.

The Blueprint creates an Ohio web service and a private PostgreSQL database on Render's free plans. The free database expires after 30 days. Render manages HTTPS and the application uses its internal database URL. The hosted database starts empty.

## Deploy on a team host

You need a host running Docker Compose, a DNS name pointed at that host, and inbound ports 80 and 443 for Caddy. Run these from the repo root on that host. Set `MIP_DOMAIN` to the team's hostname and generate a unique hex database password.

```bash
umask 077
printf 'MIP_DOMAIN=mip.example.com\nMIP_DB_PASSWORD=%s\n' "$(openssl rand -hex 32)" > .env
# Edit .env to use your actual hostname.
docker compose up -d --build
docker compose ps
docker compose exec app python -m scripts.manage_account create-admin teamadmin
```

Compose keeps PostgreSQL and Uvicorn on private container networks. Caddy terminates HTTPS and redirects the root URL to the dashboard. The app applies versioned SQL migrations before Uvicorn starts and sets an HTTPS-only session cookie in this deployment. Existing Day 3–10 catalog rows are kept by the baseline migration. For an existing production database, take a backup before upgrading. Keep the generated `.env` private and do not recreate it on later deployments.

After deployment, open your HTTPS URL, sign in, create a viewer, and verify that the viewer can compare offers and receives `403` on writes.

## Back up and restore

From the repository root on the host, create a custom-format PostgreSQL dump. The dump includes team account password hashes and catalog data. Store it in protected storage outside the host.

```bash
umask 077
mkdir -p backups
docker compose exec -T db pg_dump -U mip -d mip -Fc > "backups/mip-$(date +%Y%m%d-%H%M%S).dump"
```

Restore into a **new empty database** first. Replace the filename with the actual dump.

```bash
docker compose exec -T db createdb -U mip mip_restore
docker compose exec -T db pg_restore -U mip -d mip_restore --exit-on-error < backups/your-backup.dump
docker compose exec -T db psql -U mip -d mip_restore -v ON_ERROR_STOP=1 \
  -c 'TRUNCATE team_sessions, login_attempts, customer_invitations' \
  -c 'SELECT count(*) AS products FROM products' \
  -c 'SELECT count(*) AS offers FROM vendor_products'
```

To cut over after verification, stop the app, keep the original database as a rollback point, and change the app's `DATABASE_URL` database name in Compose to `mip_restore`. Then recreate the app service and confirm you can sign in and compare offers. Restored users must sign in again.

## Sourcing API

| Method | Path | Result |
|---|---|---|
| PUT | `/vendors/{vendor_id}` | Replace vendor code and name |
| POST | `/vendors/{vendor_id}/products/{product_id}` | Link a supplier and product with optional terms |
| GET | `/vendors/{vendor_id}/products` | List a vendor's products |
| PUT | `/vendors/{vendor_id}/products/{product_id}` | Replace unit price in USD and lead time in days |
| DELETE | `/vendors/{vendor_id}/products/{product_id}` | Remove a sourcing link |
| GET | `/products/{product_id}/suppliers` | Compare suppliers for a product |

Term values look like `{"unit_price":"8.40","lead_time_days":12}`. With `PUT`, omitted or null values clear the corresponding term. Prices use decimal amounts and are returned as JSON strings. A duplicate link returns `409`. A missing record or link returns `404`.

## Run the integration checks

From the repo root, run `bash backend/tests/run_team_smoke.sh` with PostgreSQL client and server tools installed. Set `PG_BIN` to their directory if `pg_config` is unavailable. The script uses a disposable PostgreSQL instance and loopback port 8014. It exercises migrations, team permissions, the full sourcing workflow, two-company customer access, shop-floor workflows, and a real backup and restore.

## Investigate rejected parts

Open **Production** and select **Investigate rejects** on a run with rejects. The investigation shows the current rate, the weighted reject rate across up to 10 prior runs for the same machine and part, recent inspection notes, and matching approved work instructions. A procedure is a written instruction, such as an inspection checklist or your rejected-parts handling process. Use **Ask Manufacturing → Manage procedures** to add approved text.

With the OpenAI API key configured, the assistant drafts a supervisor handoff with citations, evidence gaps, and checks for the reviewer. Staff review the draft and decide what action to take. Without the key, the screen still provides the calculated rates and source evidence. For a walkthrough, use the sample runs in a demo database.

## Ask Manufacturing

Run the database migrations and open **Ask Manufacturing** from the staff dashboard. An administrator can add approved plain-text procedures through **Manage procedures**. Start with a sample procedure such as “Quarantine rejected brackets in the red inspection bin and record the batch reference.” Ask where rejected brackets should go and open the source passage.

The app splits procedures into overlapping passages, indexes them with PostgreSQL full-text search, and retrieves the best matches. **Production records** uses a fixed, read-only SQL query for the selected period and returns up to 50 machines ordered by rejects. **Procedures and production** combines both sources. The LLM receives the selected evidence and question and returns text with source IDs. The server checks that each cited ID exists in the evidence.

To enable generation, add `OPENAI_API_KEY` to `backend/.env` for local development or the deployment Compose `.env`, then restart the app. Set `MIP_LLM_MODEL` to choose a different Responses API model. Without a key, the page still displays the evidence it retrieved. With a key, questions and retrieved excerpts or production aggregates are sent to OpenAI. Start with synthetic data for the walkthrough.

For an FDE demo, ask the same procedure question before and after adding the document. Then choose **Procedures and production**, select a period with recorded runs, and compare the answer with both source types. Finally, remove the procedure and repeat the question to check that its source disappears.
