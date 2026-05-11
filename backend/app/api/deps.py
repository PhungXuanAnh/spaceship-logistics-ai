"""FastAPI dependencies: DB session, current user, tenant context."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.db.models import User
from app.db.session import SessionLocal
from app.repositories.base import Filters
from app.repositories.sqlalchemy_orders import SqlAlchemyOrderRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_db_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db_session),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad token payload")
    user = db.query(User).filter(User.email == sub).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_repo(db: Session = Depends(get_db_session)) -> SqlAlchemyOrderRepository:
    return SqlAlchemyOrderRepository(db)


def get_effective_client_id(
    user: User = Depends(get_current_user),
    view_as: str | None = Query(default=None, description="Admin: view as client_id"),
) -> str | None:
    """Returns the tenant scope to apply.

    - Non-admin user: locked to their own client_id (cannot override).
    - Admin user: may pass ?view_as=CL-XXXX to scope to one client; None = all clients.
    """
    if user.is_admin:
        return view_as or None
    return user.client_id


def get_filters(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    carrier: list[str] | None = Query(default=None),
    region: list[str] | None = Query(default=None),
    category: list[str] | None = Query(default=None),
    warehouse: list[str] | None = Query(default=None),
    sku: list[str] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    client_id: str | None = Depends(get_effective_client_id),
) -> Filters:
    return Filters(
        client_id=client_id,
        date_from=date_from,
        date_to=date_to,
        carrier=carrier or [],
        region=region or [],
        category=category or [],
        warehouse=warehouse or [],
        sku=sku or [],
        status=status or [],
    )
