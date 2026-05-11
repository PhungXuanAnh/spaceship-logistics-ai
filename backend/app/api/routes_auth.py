"""Auth routes: POST /api/auth/login, GET /api/auth/me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_session
from app.auth.security import create_access_token, verify_password
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserOut(BaseModel):
    id: int
    email: str
    is_admin: bool
    client_id: str | None


@router.post("/login", response_model=TokenOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db_session),
):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    token = create_access_token(subject=user.email, extra={"is_admin": user.is_admin})
    return TokenOut(
        access_token=token,
        user={
            "id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
            "client_id": user.client_id,
        },
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, is_admin=user.is_admin, client_id=user.client_id)
