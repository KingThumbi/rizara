ROLE_CREATION_RULES = {
    "super_admin": [
        "admin", "staff", "farmer", "buyer",
        "transporter", "veterinary", "agronomist", "processor"
    ],
    "admin": [
        "staff", "farmer", "buyer",
        "transporter", "veterinary", "agronomist", "processor"
    ]
}
