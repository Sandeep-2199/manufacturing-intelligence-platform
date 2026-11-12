import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import LoginAttempt, TeamSession, TeamUser
from app.schemas.account import AccountCreate, AccountResponse, Credentials
from app.services.security import (
    COOKIE_NAME,
    SECURE_COOKIE,
    current_user,
    hash_password,
    require_admin,
    token_digest,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["Team access"])
admin = APIRouter(prefix="/team", tags=["Team access"], dependencies=[Depends(require_admin)])
SESSION_SECONDS = 8 * 60 * 60


@router.post("/login", response_model=AccountResponse)
def login(credentials: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    db.execute(delete(LoginAttempt).where(LoginAttempt.expires_at <= now))
    attempt = insert(LoginAttempt).values(
        client_ip=request.client.host, attempts=1, expires_at=now + timedelta(minutes=1)
    )
    count = db.scalar(
        attempt.on_conflict_do_update(
            index_elements=["client_ip"],
            set_={"attempts": LoginAttempt.attempts + 1},
            where=LoginAttempt.attempts < 13,
        ).returning(LoginAttempt.attempts)
    )
    db.commit()
    if count is None or count > 12:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again in a minute.")

    user = db.scalar(select(TeamUser).where(TeamUser.username == credentials.username).with_for_update())
    if not verify_password(credentials.password.get_secret_value(), user.password_hash if user else None):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    previous = request.cookies.get(COOKIE_NAME)
    if previous:
        db.execute(delete(TeamSession).where(TeamSession.token_hash == token_digest(previous)))
    db.execute(delete(TeamSession).where(TeamSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    db.add(TeamSession(
        token_hash=token_digest(token),
        user_id=user.user_id,
        expires_at=now + timedelta(seconds=SESSION_SECONDS),
    ))
    account = AccountResponse.model_validate(user)
    db.commit()
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True, secure=SECURE_COOKIE,
        samesite="strict", path="/",
    )
    return account


@router.get("/me", response_model=AccountResponse)
def who_am_i(user: TeamUser = Depends(current_user)):
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute(delete(TeamSession).where(TeamSession.token_hash == token_digest(token)))
        db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", secure=SECURE_COOKIE, httponly=True, samesite="strict")
    return response


@admin.get("/users", response_model=list[AccountResponse])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(TeamUser).where(TeamUser.role != "customer").order_by(TeamUser.username)).all()


@admin.post("/users", response_model=AccountResponse, status_code=201)
def create_user(account: AccountCreate, db: Session = Depends(get_db)):
    statement = (
        insert(TeamUser)
        .values(
            username=account.username,
            password_hash=hash_password(account.password.get_secret_value()),
            role=account.role,
            is_active=True,
        )
        .on_conflict_do_nothing(index_elements=["username"])
        .returning(TeamUser)
    )
    user = db.scalar(statement)
    if user is None:
        raise HTTPException(status_code=409, detail="Username already exists")
    response = AccountResponse.model_validate(user)
    db.commit()
    return response
