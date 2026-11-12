"""Add demo products, vendors, and supplier terms without replacing existing data."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal
from app.models.product import Product
from app.models.vendor import Vendor
from app.models.vendor_product import VendorProduct


PRODUCTS = [
    {
        "part_number": "DEMO-BRK-100",
        "product_name": "Mounting Bracket",
        "description": "Aluminum mounting bracket for machine frames",
        "material": "Aluminum 6061",
        "unit": "piece",
    },
    {
        "part_number": "DEMO-SHF-200",
        "product_name": "Drive Shaft",
        "description": "Steel shaft for drive assemblies",
        "material": "Steel 4140",
        "unit": "piece",
    },
    {
        "part_number": "DEMO-SPC-300",
        "product_name": "Bearing Spacer",
        "material": "Stainless Steel",
        "unit": "piece",
    },
]

VENDORS = [
    {"vendor_code": "DEMO-PRE", "vendor_name": "Precision Metals"},
    {"vendor_code": "DEMO-APX", "vendor_name": "Apex Machining"},
    {"vendor_code": "DEMO-NOR", "vendor_name": "Northline Components"},
]

OFFERS = [
    ("DEMO-BRK-100", "DEMO-PRE", Decimal("8.40"), 12),
    ("DEMO-BRK-100", "DEMO-APX", Decimal("9.75"), 5),
    ("DEMO-BRK-100", "DEMO-NOR", Decimal("8.95"), 8),
    ("DEMO-SHF-200", "DEMO-PRE", Decimal("24.60"), 14),
    ("DEMO-SHF-200", "DEMO-NOR", None, None),
]


def seed_demo():
    with SessionLocal.begin() as db:
        for product in PRODUCTS:
            db.execute(
                insert(Product)
                .values(**product)
                .on_conflict_do_nothing(index_elements=["part_number"])
            )

        db.execute(
            insert(Vendor).values(VENDORS).on_conflict_do_nothing(index_elements=["vendor_code"])
        )
        product_ids = dict(
            db.execute(
                select(Product.part_number, Product.product_id)
                .where(Product.part_number.in_([product["part_number"] for product in PRODUCTS]))
            ).all()
        )
        vendor_ids = dict(
            db.execute(
                select(Vendor.vendor_code, Vendor.vendor_id)
                .where(Vendor.vendor_code.in_([vendor["vendor_code"] for vendor in VENDORS]))
            ).all()
        )
        links = [
            {
                "product_id": product_ids[part_number],
                "vendor_id": vendor_ids[vendor_code],
                "unit_price": unit_price,
                "lead_time_days": lead_time_days,
            }
            for part_number, vendor_code, unit_price, lead_time_days in OFFERS
        ]
        db.execute(
            insert(VendorProduct)
            .values(links)
            .on_conflict_do_nothing(index_elements=["vendor_id", "product_id"])
        )
    print("Demo products and supplier offers are ready.")


if __name__ == "__main__":
    seed_demo()
