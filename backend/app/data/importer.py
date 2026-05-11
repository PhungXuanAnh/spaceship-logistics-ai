"""CSV importer CLI: idempotent truncate-and-load."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.auth.security import hash_password
from app.db.models import Order, User
from app.db.session import Base, SessionLocal, engine
from app.settings import get_settings


def _to_date(v):
    if pd.isna(v) or v == "":
        return None
    if isinstance(v, str):
        return datetime.strptime(v, "%Y-%m-%d").date()
    return v


def import_csv(csv_path: str | Path) -> int:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    Base.metadata.create_all(bind=engine)

    df = pd.read_csv(csv_path)
    df["order_date"] = df["order_date"].apply(_to_date)
    df["delivery_date"] = df["delivery_date"].apply(_to_date)
    df["is_promo"] = df["is_promo"].astype(bool)

    with SessionLocal() as session:
        # Truncate orders (read-only dataset; safe to wipe + reload)
        session.execute(text("DELETE FROM orders"))
        session.commit()

        rows = []
        for _, r in df.iterrows():
            rows.append(
                Order(
                    client_id=r["client_id"],
                    order_id=r["order_id"],
                    order_date=r["order_date"],
                    delivery_date=r["delivery_date"],
                    carrier=r["carrier"],
                    origin_city=r["origin_city"],
                    destination_city=r["destination_city"],
                    status=r["status"],
                    sku=r["sku"],
                    product_category=r["product_category"],
                    quantity=int(r["quantity"]),
                    unit_price_usd=float(r["unit_price_usd"]),
                    order_value_usd=float(r["order_value_usd"]),
                    is_promo=bool(r["is_promo"]),
                    promo_discount_pct=float(r["promo_discount_pct"]),
                    region=r["region"],
                    warehouse=r["warehouse"],
                )
            )
        session.bulk_save_objects(rows)
        session.commit()

        _seed_demo_user(session)

    print(f"[importer] inserted {len(rows)} orders from {csv_path}")
    return len(rows)


def _seed_demo_user(session) -> None:
    settings = get_settings()
    existing = session.query(User).filter(User.email == settings.demo_user_email).first()
    if existing:
        return
    user = User(
        email=settings.demo_user_email,
        hashed_password=hash_password(settings.demo_user_password),
        is_admin=True,
        client_id=settings.demo_user_client_id or None,
    )
    session.add(user)
    session.commit()
    print(f"[importer] seeded demo user {settings.demo_user_email}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/mock_logistics_data.csv"
    import_csv(path)
