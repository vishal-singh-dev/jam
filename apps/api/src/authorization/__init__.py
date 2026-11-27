"""Authorization package for the Collaborative Whiteboard application.

Provides decoupled role definitions, granular permissions, policy evaluation,
and domain exceptions.
"""

from src.authorization.exceptions import (
    AuthorizationError,
    InsufficientPermissionError,
    InvalidRoleError,
    LastOwnerProtectionError,
)
from src.authorization.policies import (
    can_mutate_canvas_content,
    has_board_permission,
    require_board_permission,
    validate_owner_count_invariant,
)
from src.authorization.roles import (
    ROLE_PERMISSIONS,
    BoardPermission,
    BoardRole,
    parse_role,
)

__all__ = [
    "AuthorizationError",
    "BoardPermission",
    "BoardRole",
    "InsufficientPermissionError",
    "InvalidRoleError",
    "LastOwnerProtectionError",
    "ROLE_PERMISSIONS",
    "can_mutate_canvas_content",
    "has_board_permission",
    "parse_role",
    "require_board_permission",
    "validate_owner_count_invariant",
]
