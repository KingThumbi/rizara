from __future__ import annotations

from app.models import Goat, Sheep, Cattle


ANIMAL_MODEL_MAP = {
    "goat": Goat,
    "sheep": Sheep,
    "cattle": Cattle,
}

PROCESSING_RELATION_MAP = {
    "goat": "goats",
    "sheep": "sheep",
    "cattle": "cattle",
}


def get_animal_model(animal_type: str):
    model = ANIMAL_MODEL_MAP.get((animal_type or "").strip().lower())
    if model is None:
        raise ValueError(f"Unsupported animal type: {animal_type}")
    return model


def get_processing_relation_name(animal_type: str) -> str:
    relation = PROCESSING_RELATION_MAP.get((animal_type or "").strip().lower())
    if relation is None:
        raise ValueError(f"Unsupported animal type: {animal_type}")
    return relation


def animal_label(animal_type: str) -> str:
    return (animal_type or "").strip().capitalize()