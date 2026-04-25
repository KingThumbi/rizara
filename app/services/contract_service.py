from __future__ import annotations

from decimal import Decimal

from app.models import Contract


def generate_contract_number() -> str:
    last_contract = (
        Contract.query
        .order_by(Contract.id.desc())
        .first()
    )

    next_id = 1 if not last_contract else last_contract.id + 1
    return f"CTR-{next_id:05d}"


def calculate_contract_totals(contract: Contract) -> dict:
    contracted_qty = Decimal("0.00")
    contracted_value = Decimal("0.00")
    sold_qty = Decimal("0.00")
    sold_value = Decimal("0.00")

    for item in contract.items:
        contracted_qty += Decimal(item.quantity or 0)
        contracted_value += Decimal(item.total_price or 0)

    for sale in contract.sales:
        for item in sale.items:
            sold_qty += Decimal(item.quantity or 0)
            sold_value += Decimal(item.line_total or 0)

    remaining_qty = contracted_qty - sold_qty
    remaining_value = contracted_value - sold_value

    return {
        "contracted_qty": contracted_qty,
        "contracted_value": contracted_value,
        "sold_qty": sold_qty,
        "sold_value": sold_value,
        "remaining_qty": remaining_qty,
        "remaining_value": remaining_value,
    }


def can_submit_contract_for_review(contract: Contract) -> tuple[bool, str]:
    if contract.status != "draft":
        return False, "Only draft contracts can be submitted for review."
    if not contract.buyer_id:
        return False, "Contract must have a buyer."
    if not contract.items:
        return False, "Add at least one contract item before submitting."
    return True, ""


def can_approve_contract(contract: Contract) -> tuple[bool, str]:
    if contract.status != "under_review":
        return False, "Only contracts under review can be approved."
    return True, ""


def can_mark_signed(contract: Contract) -> tuple[bool, str]:
    if contract.status not in {"approved", "sent"}:
        return False, "Only approved or sent contracts can be marked signed."

    has_signed_doc = any(
        d.document_type in {"signed_contract", "executed_contract"} for d in contract.documents
    )
    if not has_signed_doc:
        return False, "Upload a signed contract document first."

    return True, ""


def can_activate_contract(contract: Contract) -> tuple[bool, str]:
    if contract.status != "signed":
        return False, "Only signed contracts can be activated."
    return True, ""