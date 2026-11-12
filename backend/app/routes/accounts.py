import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import LoginAttempt, TeamSession, TeamUser
from app.schemas.account import AccountCreate, AccountResponse, Credentials, PasswordReset, Username
from app.services.recovery import recovery_email, send_reset_email
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
RESET_LIFETIME = timedelta(minutes=20)


@router.post("/password-reset/request", status_code=202)
def request_password_reset(account: Username, db: Session = Depends(get_db)):
    recipient = recovery_email()
    if not recipient:
        raise HTTPException(503, "Password recovery is unavailable. Contact your administrator.")
    message = {"message": "If recovery is configured for this account, check your inbox for a reset link."}
    if account.username != "teamadmin":
        return message

    now = datetime.now(timezone.utc)
    user = db.scalar(select(TeamUser).where(
        TeamUser.username == account.username, TeamUser.is_active.is_(True), TeamUser.role == "admin",
    ).with_for_update())
    if user is None or (user.reset_expires_at and user.reset_expires_at > now):
        return message

    token = secrets.token_urlsafe(32)
    digest = token_digest(f"{recipient}:{token}")
    user.reset_token_hash = digest
    user.reset_expires_at = now + RESET_LIFETIME
    db.commit()
    if not send_reset_email(recipient, token):
        failed = db.scalar(select(TeamUser).where(
            TeamUser.reset_token_hash == digest,
        ).with_for_update())
        if failed:
            failed.reset_token_hash = None
            failed.reset_expires_at = now + timedelta(minutes=1)
        db.commit()
    return message


@router.post("/password-reset/confirm", status_code=204)
def confirm_password_reset(reset: PasswordReset, db: Session = Depends(get_db)):
    recipient = recovery_email()
    if not recipient:
        raise HTTPException(503, "Password recovery is unavailable. Contact your administrator.")
    user = db.scalar(select(TeamUser).where(
        TeamUser.username == "teamadmin", TeamUser.role == "admin", TeamUser.is_active.is_(True),
        TeamUser.reset_token_hash == token_digest(f"{recipient}:{reset.token.get_secret_value()}"),
        TeamUser.reset_expires_at > datetime.now(timezone.utc),
    ).with_for_update())
    if user is None:
        raise HTTPException(400, "This reset link is invalid or has expired.")
    user.password_hash = hash_password(reset.password.get_secret_value())
    user.reset_token_hash = None
    user.reset_expires_at = None
    db.execute(delete(TeamSession).where(TeamSession.user_id == user.user_id))
    db.commit()


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
