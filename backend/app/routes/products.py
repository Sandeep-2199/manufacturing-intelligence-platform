
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductResponse, ProductUpdate


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


# Create a new product
@router.post("/", response_model=ProductResponse, status_code=201)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db)
):

    new_product = Product(
        part_number=product.part_number,
        product_name=product.product_name,
        description=product.description,
        material=product.material,
        unit=product.unit
    )

    db.add(new_product)

    try:
        db.commit()
        db.refresh(new_product)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="A product with this part number already exists"
        )

    return new_product


# Retrieve all products
@router.get("/", response_model=list[ProductResponse])
def get_products(db: Session = Depends(get_db)):

    products = db.query(Product).all()

    return products


def _get_product_or_404(product_id: int, db: Session) -> Product:
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    return product


# Retrieve one product using its ID
@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    return _get_product_or_404(product_id, db)


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    update: ProductUpdate,
    db: Session = Depends(get_db)
):
    product = _get_product_or_404(product_id, db)

    for field, value in update.model_dump().items():
        setattr(product, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A product with this part number already exists"
        ) from exc

    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204)
def deactivate_product(product_id: int, db: Session = Depends(get_db)) -> Response:
    product = _get_product_or_404(product_id, db)
    product.is_active = False
    db.commit()
    return Response(status_code=204)
