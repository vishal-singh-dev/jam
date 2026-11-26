"""Unit and policy tests for the decoupled authorization package."""

import pytest

from src.authorization.exceptions import (
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


def test_board_role_enumeration() -> None:
    """Verify supported board roles."""
    assert BoardRole.OWNER.value == "owner"
    assert BoardRole.EDITOR.value == "editor"
    assert BoardRole.VIEWER.value == "viewer"


def test_parse_role_valid() -> None:
    """parse_role accepts valid lowercase, uppercase, and enum roles."""
    assert parse_role("owner") == BoardRole.OWNER
    assert parse_role("EDITOR") == BoardRole.EDITOR
    assert parse_role("  viewer  ") == BoardRole.VIEWER
    assert parse_role(BoardRole.OWNER) == BoardRole.OWNER


def test_parse_role_invalid() -> None:
    """parse_role raises ValueError for unsupported roles."""
    with pytest.raises(ValueError, match="Invalid board role"):
        parse_role("admin")

    with pytest.raises(ValueError, match="Invalid board role"):
        parse_role("contributor")


def test_role_permissions_matrix() -> None:
    """Verify granular permissions mapped to each role."""
    # Viewer: read-only
    viewer_perms = ROLE_PERMISSIONS[BoardRole.VIEWER]
    assert BoardPermission.READ_BOARD in viewer_perms
    assert BoardPermission.VIEW_MEMBERS in viewer_perms
    assert BoardPermission.VIEW_CONTENT in viewer_perms
    assert BoardPermission.MUTATE_CONTENT not in viewer_perms
    assert BoardPermission.DELETE_BOARD not in viewer_perms
    assert BoardPermission.MANAGE_MEMBERS not in viewer_perms

    # Editor: content mutation and assets, but no board lifecycle/management
    editor_perms = ROLE_PERMISSIONS[BoardRole.EDITOR]
    assert BoardPermission.MUTATE_CONTENT in editor_perms
    assert BoardPermission.ATTACH_ASSETS in editor_perms
    assert BoardPermission.REMOVE_ASSETS in editor_perms
    assert BoardPermission.MANAGE_MEMBERS not in editor_perms
    assert BoardPermission.TRANSFER_OWNERSHIP not in editor_perms
    assert BoardPermission.DELETE_BOARD not in editor_perms

    # Owner: full permissions
    owner_perms = ROLE_PERMISSIONS[BoardRole.OWNER]
    for perm in BoardPermission:
        assert perm in owner_perms


def test_has_board_permission() -> None:
    """has_board_permission returns True for granted and False for denied."""
    assert has_board_permission(BoardRole.OWNER, BoardPermission.DELETE_BOARD) is True
    assert has_board_permission(BoardRole.EDITOR, BoardPermission.DELETE_BOARD) is False
    assert has_board_permission(BoardRole.VIEWER, BoardPermission.MUTATE_CONTENT) is False
    assert has_board_permission(BoardRole.EDITOR, BoardPermission.MUTATE_CONTENT) is True
    assert has_board_permission("invalid-role", BoardPermission.READ_BOARD) is False


def test_require_board_permission_success() -> None:
    """require_board_permission does not raise for authorized role."""
    require_board_permission(BoardRole.OWNER, BoardPermission.DELETE_BOARD)
    require_board_permission(BoardRole.EDITOR, BoardPermission.MUTATE_CONTENT)
    require_board_permission(BoardRole.VIEWER, BoardPermission.READ_BOARD)


def test_require_board_permission_denied() -> None:
    """require_board_permission raises InsufficientPermissionError when unauthorized."""
    with pytest.raises(InsufficientPermissionError) as exc_info:
        require_board_permission(BoardRole.VIEWER, BoardPermission.MUTATE_CONTENT)
    assert exc_info.value.role == "viewer"
    assert exc_info.value.required_permission == BoardPermission.MUTATE_CONTENT.value

    with pytest.raises(InsufficientPermissionError) as exc_info:
        require_board_permission(BoardRole.EDITOR, BoardPermission.TRANSFER_OWNERSHIP)
    assert exc_info.value.role == "editor"


def test_require_board_permission_invalid_role() -> None:
    """require_board_permission raises InvalidRoleError for unrecognized roles."""
    with pytest.raises(InvalidRoleError):
        require_board_permission("superadmin", BoardPermission.READ_BOARD)


def test_can_mutate_canvas_content() -> None:
    """can_mutate_canvas_content enforces viewer read-only rule."""
    assert can_mutate_canvas_content(BoardRole.OWNER) is True
    assert can_mutate_canvas_content(BoardRole.EDITOR) is True
    assert can_mutate_canvas_content(BoardRole.VIEWER) is False


def test_last_owner_protection_invariant() -> None:
    """validate_owner_count_invariant prevents removing or demoting the last owner."""
    # When multiple owners exist, removing an owner is permitted
    validate_owner_count_invariant(
        current_owners_count=2,
        is_removing_or_demoting_owner=True,
    )

    # When only 1 owner exists, removing or demoting raises LastOwnerProtectionError
    with pytest.raises(LastOwnerProtectionError, match="Cannot remove or demote the last owner"):
        validate_owner_count_invariant(
            current_owners_count=1,
            is_removing_or_demoting_owner=True,
            board_id="board-test-id",
        )

    # When not removing an owner (e.g. modifying an editor), no error even with 1 owner
    validate_owner_count_invariant(
        current_owners_count=1,
        is_removing_or_demoting_owner=False,
    )
