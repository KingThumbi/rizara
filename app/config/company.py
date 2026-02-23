# app/config/company.py
from __future__ import annotations

"""
Single source of truth for Rizara company identity.

Goals:
- Keep backward compatibility with existing code that expects COMPANY_PROFILE (dict).
- Provide normalized, template-friendly constants and helper context.
- Avoid formatting differences across HTML/PDF outputs.
"""

# -----------------------------
# Canonical fields (preferred)
# -----------------------------
COMPANY_NAME = "Rizara Meats Ltd"
COMPANY_TAGLINE = "Ethical • Traceable • Halal"

# Keep the address as a single display line (PDF-friendly)
COMPANY_ADDRESS = "P.O Box 25399-00100 Nairobi, Kenya"

COMPANY_EMAIL = "sales@rizara.co.ke"

# If you truly use multiple phone numbers, keep both:
COMPANY_PHONES = ["+254-700-912-362", "+254-780-912-362"]

# “Primary” phone for single-line places (headers/footers)
COMPANY_PHONE = COMPANY_PHONES[0]

# Website without protocol (matches what you used)
COMPANY_WEBSITE = "www.rizara.co.ke"


# -----------------------------
# Backward compatible profile
# -----------------------------
# NOTE: keep keys stable: name/email/phones/po_box/website
# For "po_box", we keep the older GPO format because your template might print it verbatim.
COMPANY_PROFILE = {
    "name": COMPANY_NAME,
    "email": COMPANY_EMAIL,
    "phones": " / ".join(COMPANY_PHONES),
    "po_box": "P.O. Box 25399-00100, GPO Nairobi",
    "website": COMPANY_WEBSITE,
    # Extra keys (safe additions; won't break old callers)
    "tagline": COMPANY_TAGLINE,
    "address": COMPANY_ADDRESS,
    "phone_primary": COMPANY_PHONE,
    "phones_list": COMPANY_PHONES,
}


def company_context() -> dict:
    """
    Recommended template/PDF context injection.

    Gives both:
    - NEW keys: COMPANY_NAME, COMPANY_EMAIL, etc.
    - OLD dict: COMPANY_PROFILE
    """
    return {
        # New preferred keys
        "COMPANY_NAME": COMPANY_NAME,
        "COMPANY_TAGLINE": COMPANY_TAGLINE,
        "COMPANY_ADDRESS": COMPANY_ADDRESS,
        "COMPANY_EMAIL": COMPANY_EMAIL,
        "COMPANY_PHONE": COMPANY_PHONE,
        "COMPANY_PHONES": COMPANY_PHONES,
        "COMPANY_WEBSITE": COMPANY_WEBSITE,
        # Back-compat
        "COMPANY_PROFILE": COMPANY_PROFILE,
    }