"""Authorization roles and permissions enumeration for the Collaborative Whiteboard.

This module is intentionally separated from application routers, database models,
and business logic to ensure strict decoupling of authorization boundaries.
"""

from enum import StrEnum


class BoardRole(StrEnum):
    """Board member roles representing authorization tiers."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class BoardPermission(StrEnum):
    """Granular board-level permissions enforced across API and collaboration layers."""

    # Board lifecycle & metadata
    READ_BOARD = "board:read"
    UPDATE_METADATA = "board:update_metadata"
    DELETE_BOARD = "board:delete"
    TRANSFER_OWNERSHIP = "board:transfer_ownership"

    # Membership management
    VIEW_MEMBERS = "board:view_members"
    MANAGE_MEMBERS = "board:manage_members"

    # Content & Collaboration
    VIEW_CONTENT = "board:view_content"
    MUTATE_CONTENT = "board:mutate_content"

    # Asset attachments
    ATTACH_ASSETS = "board:attach_assets"
    REMOVE_ASSETS = "board:remove_assets"


# Explicit Role-to-Permission mapping matrix
ROLE_PERMISSIONS: dict[BoardRole, frozenset[BoardPermission]] = {
    BoardRole.VIEWER: frozenset(
        {
            BoardPermission.READ_BOARD,
            BoardPermission.VIEW_MEMBERS,
            BoardPermission.VIEW_CONTENT,
        }
    ),
    BoardRole.EDITOR: frozenset(
        {
            BoardPermission.READ_BOARD,
            BoardPermission.VIEW_MEMBERS,
            BoardPermission.VIEW_CONTENT,
            BoardPermission.MUTATE_CONTENT,
            BoardPermission.ATTACH_ASSETS,
            BoardPermission.REMOVE_ASSETS,
        }
    ),
    BoardRole.OWNER: frozenset(
        {
            BoardPermission.READ_BOARD,
            BoardPermission.UPDATE_METADATA,
            BoardPermission.DELETE_BOARD,
            BoardPermission.TRANSFER_OWNERSHIP,
            BoardPermission.VIEW_MEMBERS,
            BoardPermission.MANAGE_MEMBERS,
            BoardPermission.VIEW_CONTENT,
            BoardPermission.MUTATE_CONTENT,
            BoardPermission.ATTACH_ASSETS,
            BoardPermission.REMOVE_ASSETS,
        }
    ),
}


def parse_role(role_val: str | BoardRole) -> BoardRole:
    """Parse a string or enum into a validated BoardRole."""
    if isinstance(role_val, BoardRole):
        return role_val
    try:
        return BoardRole(role_val.lower().strip())
    except (ValueError, AttributeError) as exc:
        valid = [r.value for r in BoardRole]
        raise ValueError(f"Invalid board role: '{role_val}'. Valid roles: {valid}") from exc
