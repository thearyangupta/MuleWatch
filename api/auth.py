"""JWT authentication for MuleWatch's analyst console."""

import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
password_hash = PasswordHash.recommended()

Role = Literal["analyst", "lead"]
ALGORITHM = "HS256"
TOKEN_MINUTES = 30


class AuthenticatedUser(BaseModel):
    username: str
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def signing_secret() -> str:
    secret = os.getenv("MULEWATCH_JWT_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "JWT authentication is not configured")
    return secret


def configured_users() -> dict[str, tuple[str, Role]]:
    users: dict[str, tuple[str, Role]] = {}

    for role in ("analyst", "lead"):
        username = os.getenv(f"MULEWATCH_{role.upper()}_USERNAME", "").strip()
        hashed = os.getenv(f"MULEWATCH_{role.upper()}_PASSWORD_HASH", "")

        if not username or not hashed:
            raise HTTPException(503, "JWT users are not configured")

        if username in users:
            raise HTTPException(503, "Duplicate authentication usernames")

        users[username] = (hashed, role)

    return users


def authenticate(username: str, password: str) -> AuthenticatedUser:
    users = configured_users()
    record = users.get(username)

    if record is None:
        raise HTTPException(401, "Invalid username or password")

    hashed, role = record

    try:
        valid = password_hash.verify(password, hashed)
    except ValueError, TypeError:
        raise HTTPException(503, "Invalid password hash configuration") from None

    if not valid:
        raise HTTPException(401, "Invalid username or password")

    return AuthenticatedUser(username=username, role=role)


def create_access_token(user: AuthenticatedUser) -> str:
    now = datetime.now(timezone.utc)

    return jwt.encode(
        {
            "sub": user.username,
            "role": user.role,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=TOKEN_MINUTES),
        },
        signing_secret(),
        algorithm=ALGORITHM,
    )


def current_user(token: str = Depends(oauth2_scheme)) -> AuthenticatedUser:
    secret = signing_secret()

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "role", "iat", "nbf", "exp"]},
        )
    except InvalidTokenError:
        raise HTTPException(401, "Invalid or expired access token") from None

    username = payload.get("sub")
    role = payload.get("role")

    if not isinstance(username, str) or role not in ("analyst", "lead"):
        raise HTTPException(401, "Invalid access token claims")

    users = configured_users()
    record = users.get(username)

    if record is None or record[1] != role:
        raise HTTPException(401, "User is no longer authorized")

    return AuthenticatedUser(username=username, role=role)


def require_lead(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
    if user.role != "lead":
        raise HTTPException(403, "Lead role required")
    return user


@router.post("/token", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form.username, form.password)
    return TokenResponse(access_token=create_access_token(user))


@router.get("/me", response_model=AuthenticatedUser)
def get_me(user: AuthenticatedUser = Depends(current_user)):
    return user
