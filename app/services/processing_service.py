from __future__ import annotations

from app.extensions import db
from app.models import AggregationBatch, ProcessingBatch
from app.utils.animal_helpers import (
    animal_label,
    get_animal_model,
    get_processing_relation_name,
)
from app.utils.time_helpers import utcnow_naive


def get_available_processing_batches(animal_type: str):
    Model = get_animal_model(animal_type)

    return (
        db.session.query(AggregationBatch)
        .join(Model, Model.aggregation_batch_id == AggregationBatch.id)
        .filter(
            AggregationBatch.animal_type == animal_type,
            AggregationBatch.is_locked.is_(False),
            Model.status == "aggregated",
            Model.is_active.is_(True),
        )
        .distinct()
        .order_by(AggregationBatch.created_at.desc())
        .all()
    )


def create_processing_batch_from_aggregation(
    *,
    animal_type: str,
    source_batch,
    facility: str,
    slaughter_date,
    halal_cert_ref,
    created_by_user_id: int,
):
    Model = get_animal_model(animal_type)
    relation_name = get_processing_relation_name(animal_type)

    animals = (
        Model.query
        .filter(
            Model.aggregation_batch_id == source_batch.id,
            Model.status == "aggregated",
            Model.is_active.is_(True),
        )
        .order_by(Model.created_at.asc())
        .all()
    )

    if not animals:
        raise ValueError(f"No eligible {animal_label(animal_type).lower()} were found.")

    processing_batch = ProcessingBatch(
        animal_type=animal_type,
        facility=facility,
        slaughter_date=slaughter_date,
        halal_cert_ref=halal_cert_ref,
        created_by_user_id=created_by_user_id,
    )
    db.session.add(processing_batch)

    relation = getattr(processing_batch, relation_name)

    for animal in animals:
        animal.status = "processing"
        relation.append(animal)

    source_batch.is_locked = True
    source_batch.locked_at = utcnow_naive()

    return processing_batch, len(animals)