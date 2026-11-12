from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreate, VendorResponse


router = APIRouter(prefix="/vendors", tags=["Vendors"])


@router.post("/", response_model=VendorResponse, status_code=201)
def create_vendor(vendor: VendorCreate, db: Session = Depends(get_db)):
    new_vendor = Vendor(
        vendor_code=vendor.vendor_code,
        vendor_name=vendor.vendor_name,
    )
    db.add(new_vendor)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A vendor with this code already exists",
        ) from exc

    db.refresh(new_vendor)
    return new_vendor


@router.get("/", response_model=list[VendorResponse])
def list_vendors(db: Session = Depends(get_db)):
    return db.query(Vendor).order_by(Vendor.vendor_id).all()


def _get_vendor_or_404(vendor_id: int, db: Session) -> Vendor:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return vendor


@router.get("/{vendor_id}", response_model=VendorResponse)
def get_vendor(vendor_id: int, db: Session = Depends(get_db)):
    return _get_vendor_or_404(vendor_id, db)


@router.put("/{vendor_id}", response_model=VendorResponse)
def update_vendor(vendor_id: int, update: VendorCreate, db: Session = Depends(get_db)):
    vendor = _get_vendor_or_404(vendor_id, db)
    vendor.vendor_code = update.vendor_code
    vendor.vendor_name = update.vendor_name

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A vendor with this code already exists",
        ) from exc

    db.refresh(vendor)
    return vendor
