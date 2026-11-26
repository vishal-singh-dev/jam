"""Authorization policy enforcement functions.

Encapsulates all authorization decisions, permission checks, and invariants,
completely isolated from router or model layers.
"""

from src.authorization.exceptions import (
    InsufficientPermissionError,
    InvalidRoleError,
    LastOwnerProtectionError,
)
from src.authorization.roles import (
    ROLE_PERMISSIONS,
    BoardPermission,
    BoardRole,
    parse_role,
)


def has_board_permission(
    role: BoardRole | str,
    permission: BoardPermission,
) -> bool:
    """Check if a given board role possesses a specific permission."""
    try:
        resolved_role = parse_role(role)
    except ValueError:
        return False

    return permission in ROLE_PERMISSIONS.get(resolved_role, frozenset())


def require_board_permission(
    role: BoardRole | str,
    permission: BoardPermission,
) -> None:
    """Ensure a role possesses the required permission or raise InsufficientPermissionError."""
    try:
        resolved_role = parse_role(role)
    except ValueError as exc:
        raise InvalidRoleError(str(role)) from exc

    if not has_board_permission(resolved_role, permission):
        raise InsufficientPermissionError(
            required_permission=permission.value,
            role=resolved_role.value,
        )


def validate_owner_count_invariant(
    current_owners_count: int,
    is_removing_or_demoting_owner: bool,
    board_id: str | None = None,
) -> None:
    """Enforce invariant: a board must always have at least one owner."""
    if is_removing_or_demoting_owner and current_owners_count <= 1:
        raise LastOwnerProtectionError(
            board_id=board_id,
            message="Cannot remove or demote the last owner of the board",
        )


def can_mutate_canvas_content(role: BoardRole | str) -> bool:
    """Check if a user with the given role can write/mutate Yjs document canvas state.

    Viewers are strictly read-only and must be rejected at both REST and WebSocket layers.
    """
    return has_board_permission(role, BoardPermission.MUTATE_CONTENT)
