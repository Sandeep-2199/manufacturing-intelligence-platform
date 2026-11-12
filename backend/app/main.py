from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from app.database import engine
from app.routes.accounts import admin as team_router, router as auth_router
from app.routes.customers import portal as portal_router, staff as work_router
from app.services.security import require_team_access, same_origin
from app.routes.assistant import router as assistant_router
from app.routes.operations import router as operations_router
from app.routes.products import router as product_router
from app.routes.vendors import router as vendor_router
from app.routes.sourcing import router as sourcing_router


# Create FastAPI application
app = FastAPI(
    title="Manufacturing Intelligence Platform",
    description="Backend application for manufacturing and vendor operations",
    version="2.0.0",
    dependencies=[Depends(same_origin)]
)


# Register product APIs
app.include_router(auth_router)
app.include_router(team_router)
app.include_router(work_router)
app.include_router(operations_router)
app.include_router(assistant_router)
app.include_router(portal_router)
app.include_router(product_router, dependencies=[Depends(require_team_access)])
app.include_router(vendor_router, dependencies=[Depends(require_team_access)])
app.include_router(sourcing_router, dependencies=[Depends(require_team_access)])


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(("/auth/", "/team/", "/portal/invitations/")):
        errors = [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})
    return await request_validation_exception_handler(request, exc)


@app.middleware("http")
async def prevent_api_caching(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/auth", "/team", "/vendors", "/products", "/work", "/operations", "/assistant", "/portal", "/customer")):
        response.headers["Cache-Control"] = "no-store"
    return response

frontend = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/dashboard", StaticFiles(directory=frontend, html=True), name="dashboard")

@app.get("/customer/sign-in", include_in_schema=False)
def customer_portal():
    return FileResponse(frontend / "customer.html")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def home():
    return RedirectResponse("/dashboard/", status_code=302)


# Check database connection
@app.get("/health/db")
def check_database():

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {
        "database": "connected"
    }
