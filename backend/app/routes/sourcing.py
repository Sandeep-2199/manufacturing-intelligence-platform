from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.vendor_product import VendorProduct
from app.routes.products import _get_product_or_404
from app.routes.vendors import _get_vendor_or_404
from app.schemas.product import ProductResponse
from app.schemas.sourcing import (
    ProductComparison,
    SupplierOffer,
    SupplierTerms,
    VendorProductResponse,
)


router = APIRouter(tags=["Sourcing"])


@router.post(
    "/vendors/{vendor_id}/products/{product_id}",
    response_model=VendorProductResponse,
    status_code=201,
)
def link_product(
    vendor_id: int, product_id: int, db: Session = Depends(get_db),
    terms: SupplierTerms | None = None,
):
    _get_vendor_or_404(vendor_id, db)
    _get_product_or_404(product_id, db)
    statement = (
        insert(VendorProduct)
        .values(vendor_id=vendor_id, product_id=product_id, **(terms or SupplierTerms()).model_dump())
        .on_conflict_do_nothing(index_elements=["vendor_id", "product_id"])
        .returning(VendorProduct)
    )
    link = db.scalar(statement)
    if link is None:
        raise HTTPException(status_code=409, detail="Vendor already supplies this product")

    response = VendorProductResponse.model_validate(link)
    db.commit()
    return response


@router.get("/vendors/{vendor_id}/products", response_model=list[ProductResponse])
def list_vendor_products(vendor_id: int, db: Session = Depends(get_db)):
    _get_vendor_or_404(vendor_id, db)
    statement = (
        select(Product)
        .join(VendorProduct)
        .where(VendorProduct.vendor_id == vendor_id)
        .order_by(Product.part_number)
    )
    return db.scalars(statement).all()


@router.put(
    "/vendors/{vendor_id}/products/{product_id}",
    response_model=VendorProductResponse,
)
def replace_terms(
    vendor_id: int, product_id: int, terms: SupplierTerms, db: Session = Depends(get_db)
):
    statement = (
        update(VendorProduct)
        .where(VendorProduct.vendor_id == vendor_id, VendorProduct.product_id == product_id)
        .values(**terms.model_dump())
        .returning(VendorProduct)
    )
    link = db.scalar(statement)
    if link is None:
        raise HTTPException(status_code=404, detail="Vendor-product link not found")

    response = VendorProductResponse.model_validate(link)
    db.commit()
    return response


@router.delete("/vendors/{vendor_id}/products/{product_id}", status_code=204)
def unlink_product(vendor_id: int, product_id: int, db: Session = Depends(get_db)):
    statement = (
        delete(VendorProduct)
        .where(VendorProduct.vendor_id == vendor_id, VendorProduct.product_id == product_id)
        .returning(VendorProduct.product_id)
    )
    if db.scalar(statement) is None:
        raise HTTPException(status_code=404, detail="Vendor-product link not found")

    db.commit()
    return Response(status_code=204)


@router.get("/products/{product_id}/suppliers", response_model=ProductComparison)
def compare_suppliers(product_id: int, db: Session = Depends(get_db)):
    product = _get_product_or_404(product_id, db)
    statement = (
        select(Vendor, VendorProduct)
        .join(VendorProduct)
        .where(VendorProduct.product_id == product_id)
        .order_by(
            VendorProduct.unit_price.asc().nulls_last(),
            VendorProduct.lead_time_days.asc().nulls_last(),
            Vendor.vendor_code,
        )
    )
    suppliers = [
        SupplierOffer(
            vendor=vendor,
            unit_price=link.unit_price,
            lead_time_days=link.lead_time_days,
        )
        for vendor, link in db.execute(statement)
    ]
    return ProductComparison(product=product, suppliers=suppliers)
