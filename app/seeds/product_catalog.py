from app import db
from app.models import ProductCatalog

DEFAULT_PRODUCTS = [
    {
        "name": "Goat Carcass",
        "code": "GOAT-CARCASS",
        "animal_type": "goat",
        "product_type": "carcass",
        "unit": "kg",
    },
    {
        "name": "Sheep/Mutton Carcass",
        "code": "SHEEP-CARCASS",
        "animal_type": "sheep",
        "product_type": "carcass",
        "unit": "kg",
    },
    {
        "name": "Cattle/Beef Carcass",
        "code": "BEEF-CARCASS",
        "animal_type": "cattle",
        "product_type": "carcass",
        "unit": "kg",
    },
    {
        "name": "Goat Offals",
        "code": "GOAT-OFFALS",
        "animal_type": "goat",
        "product_type": "offals",
        "unit": "kg",
    },
    {
        "name": "Sheep/Mutton Offals",
        "code": "SHEEP-OFFALS",
        "animal_type": "sheep",
        "product_type": "offals",
        "unit": "kg",
    },
    {
        "name": "Cattle/Beef Offals",
        "code": "BEEF-OFFALS",
        "animal_type": "cattle",
        "product_type": "offals",
        "unit": "kg",
    },
]


def seed_product_catalog():
    created = 0
    updated = 0

    for p in DEFAULT_PRODUCTS:
        code = p.get("code")
        if not code:
            continue

        existing = ProductCatalog.query.filter_by(code=code).first()

        if existing:
            # Only update if something changed (avoids unnecessary writes)
            changed = False

            if existing.name != p["name"]:
                existing.name = p["name"]
                changed = True

            if existing.animal_type != p["animal_type"]:
                existing.animal_type = p["animal_type"]
                changed = True

            if existing.product_type != p["product_type"]:
                existing.product_type = p["product_type"]
                changed = True

            if existing.unit != p["unit"]:
                existing.unit = p["unit"]
                changed = True

            if hasattr(existing, "is_active") and not existing.is_active:
                existing.is_active = True
                changed = True

            if changed:
                updated += 1

        else:
            db.session.add(ProductCatalog(
                name=p["name"],
                code=p["code"],
                animal_type=p["animal_type"],
                product_type=p["product_type"],
                unit=p["unit"],
                is_active=True,
            ))
            created += 1

    db.session.commit()

    print(f"✅ ProductCatalog seeded: {created} created, {updated} updated")
