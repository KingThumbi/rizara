from __future__ import annotations

import uuid

from flask_login import current_user

from app.extensions import db
from app.models import AggregationBatch, Farmer, Goat, Sheep, Cattle
from app.utils.animal_helpers import get_animal_model
from app.utils.time_helpers import utcnow_naive


def generate_animals_from_market_purchase(purchase, generate_animal_code_func) -> int:
    animal_type = (purchase.animal_type or "").strip().lower()
    Model = get_animal_model(animal_type)

    batch = AggregationBatch.query.get_or_404(purchase.aggregation_batch_id)

    if (batch.animal_type or "").strip().lower() != animal_type:
        raise ValueError("Aggregation batch type does not match purchase animal type.")

    source_farmer = Farmer.query.order_by(Farmer.id.asc()).first()
    if not source_farmer:
        raise ValueError("Create at least one farmer before finalizing market purchases.")

    created = 0

    for line in purchase.lines:
        qty = int(line.qty or 0)
        if qty <= 0:
            continue

        for _ in range(qty):
            serial = created + 1
            animal = Model(
                id=uuid.uuid4(),
                farmer_tag=f"MARKET-{purchase.id}-{serial:03d}",
                rizara_id=generate_animal_code_func(animal_type, source_farmer.id),
                sex=None,
                breed=None,
                estimated_dob=None,
                farmer_id=source_farmer.id,
                status="aggregated",
                is_active=True,
                aggregation_batch_id=batch.id,
                aggregated_at=utcnow_naive(),
                aggregated_by_user_id=current_user.id,
                live_weight_kg=line.estimated_live_weight_per_head_kg,
                weight_method=(line.weight_method or "estimated").strip() or "estimated",
                purchase_price_per_head=line.unit_price_kes,
                purchase_currency="KES",
            )
            db.session.add(animal)
            created += 1

    return created