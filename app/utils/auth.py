from app.constants.permissions import ROLE_CREATION_RULES

def allowed_roles_for(user):
    return ROLE_CREATION_RULES.get(user.role, [])
