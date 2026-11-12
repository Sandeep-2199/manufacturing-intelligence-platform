import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import TeamUser
from app.models.customer import CustomerCompany, CustomerInvitation, CustomerJob
from app.schemas.account import AccountResponse
from app.schemas.customer import (
    CompanyCreate,
    CompanyResponse,
    InvitationAccept,
    InvitationCreate,
    InvitationResponse,
    JobResponse,
    JobWrite,
)
from app.services.security import current_user, hash_password, require_admin, require_team_access, token_digest


staff = APIRouter(prefix="/work", tags=["Customer operations"], dependencies=[Depends(require_team_access)])
portal = APIRouter(prefix="/portal", tags=["Customer portal"])


def get_company(company_id: int, db: Session) -> CustomerCompany:
    company = db.get(CustomerCompany, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Customer company not found")
    return company


def find_job(company_id: int, job_id: int, db: Session) -> CustomerJob:
    job = db.scalar(select(CustomerJob).where(
        CustomerJob.company_id == company_id, CustomerJob.job_id == job_id,
    ))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def company_jobs(company_id: int, db: Session):
    return db.scalars(
        select(CustomerJob).where(CustomerJob.company_id == company_id).order_by(CustomerJob.job_id.desc())
    ).all()


def require_customer(user: TeamUser = Depends(current_user)) -> TeamUser:
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="Customer access required")
    return user


@staff.get("/companies", response_model=list[CompanyResponse])
def list_companies(db: Session = Depends(get_db)):
    return db.scalars(select(CustomerCompany).order_by(CustomerCompany.name)).all()


@staff.post("/companies", response_model=CompanyResponse, status_code=201)
def create_company(data: CompanyCreate, db: Session = Depends(get_db)):
    company = db.scalar(
        insert(CustomerCompany).values(name=data.name)
        .on_conflict_do_nothing(index_elements=["name"]).returning(CustomerCompany)
    )
    if company is None:
        raise HTTPException(status_code=409, detail="Customer company already exists")
    result = CompanyResponse.model_validate(company)
    db.commit()
    return result


@staff.post(
    "/companies/{company_id}/invitations",
    response_model=InvitationResponse,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_invitation(company_id: int, data: InvitationCreate, db: Session = Depends(get_db)):
    get_company(company_id, db)
    if db.scalar(select(TeamUser.user_id).where(TeamUser.username == data.username)) is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(hours=24)
    db.add(CustomerInvitation(
        token_hash=token_digest(token), company_id=company_id, username=data.username, expires_at=expiry,
    ))
    db.commit()
    return InvitationResponse(token=token, expires_at=expiry)


@staff.get("/companies/{company_id}/jobs", response_model=list[JobResponse])
def list_company_jobs(company_id: int, db: Session = Depends(get_db)):
    get_company(company_id, db)
    return company_jobs(company_id, db)


@staff.post("/companies/{company_id}/jobs", response_model=JobResponse, status_code=201)
def create_job(company_id: int, data: JobWrite, db: Session = Depends(get_db)):
    get_company(company_id, db)
    job = CustomerJob(company_id=company_id, **data.model_dump())
    db.add(job)
    return save_job(job, db)


@staff.put("/companies/{company_id}/jobs/{job_id}", response_model=JobResponse)
def update_job(company_id: int, job_id: int, data: JobWrite, db: Session = Depends(get_db)):
    job = find_job(company_id, job_id, db)
    for field, value in data.model_dump().items():
        setattr(job, field, value)
    return save_job(job, db)


def save_job(job: CustomerJob, db: Session) -> JobResponse:
    try:
        db.flush()
        result = JobResponse.model_validate(job)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="Job reference already exists for this company") from exc
        raise
    return result


@portal.post("/invitations/accept", response_model=AccountResponse, status_code=201)
def accept_invitation(data: InvitationAccept, db: Session = Depends(get_db)):
    digest = token_digest(data.token.get_secret_value())
    invitation = db.scalar(select(CustomerInvitation).where(
        CustomerInvitation.token_hash == digest,
    ).with_for_update())
    now = datetime.now(timezone.utc)
    if invitation is None or invitation.consumed_at is not None or invitation.expires_at <= now:
        raise HTTPException(status_code=404, detail="Invitation is invalid, expired, or already used")

    user = db.scalar(
        insert(TeamUser).values(
            username=invitation.username,
            password_hash=hash_password(data.password.get_secret_value()),
            role="customer",
            company_id=invitation.company_id,
            is_active=True,
        ).on_conflict_do_nothing(index_elements=["username"]).returning(TeamUser)
    )
    if user is None:
        raise HTTPException(status_code=409, detail="Username already exists. Ask for a new invitation.")
    invitation.consumed_at = now
    result = AccountResponse.model_validate(user)
    db.commit()
    return result


@portal.get("/company", response_model=CompanyResponse)
def my_company(user: TeamUser = Depends(require_customer), db: Session = Depends(get_db)):
    return get_company(user.company_id, db)


@portal.get("/jobs", response_model=list[JobResponse])
def my_jobs(user: TeamUser = Depends(require_customer), db: Session = Depends(get_db)):
    return company_jobs(user.company_id, db)


@portal.get("/jobs/{job_id}", response_model=JobResponse)
def my_job(job_id: int, user: TeamUser = Depends(require_customer), db: Session = Depends(get_db)):
    return find_job(user.company_id, job_id, db)
