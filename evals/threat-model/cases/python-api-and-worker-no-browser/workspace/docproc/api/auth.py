import hashlib

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

from docproc.models import Partner, SessionLocal


def get_db():
    with SessionLocal() as db:
        yield db


def current_partner(x_api_key: str = Header(...), db=Depends(get_db)) -> Partner:
    digest = hashlib.sha256(x_api_key.encode()).hexdigest()
    partner = db.scalar(select(Partner).where(Partner.api_key_sha256 == digest))
    if partner is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    return partner
