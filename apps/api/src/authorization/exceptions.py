"""Authorization and permission-related domain exceptions.

These exceptions are raised by authorization policies and services
when access control rules or invariants are violated.
"""


class AuthorizationError(Exception):
    """Base class for authorization domain errors."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(message)
        self.message = message


class InsufficientPermissionError(AuthorizationError):
    """Raised when an actor lacks the required permission for an operation."""

    def __init__(
        self,
        required_permission: str,
        role: str,
        message: str | None = None,
    ):
        msg = message or f"Role '{role}' lacks required permission: '{required_permission}'"
        super().__init__(msg)
        self.required_permission = required_permission
        self.role = role


class LastOwnerProtectionError(AuthorizationError):
    """Raised when an operation would leave a board with no active owner."""

    def __init__(
        self,
        board_id: str | None = None,
        message: str = "Cannot demote or remove the last remaining owner of a board",
    ):
        super().__init__(message)
        self.board_id = board_id


class InvalidRoleError(AuthorizationError):
    """Raised when an unsupported or invalid role is supplied."""

    def __init__(self, role: str, message: str | None = None):
        msg = message or f"Supplied role '{role}' is not a valid authorization role"
        super().__init__(msg)
        self.role = role
