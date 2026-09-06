"""Domain errors with stable, user-facing messages."""


class MoneyOSError(Exception):
    """Base class for expected MoneyOS failures."""


class ValidationError(MoneyOSError):
    """Input violates a domain rule."""


class NotFoundError(MoneyOSError):
    """A requested domain object does not exist."""


class ConflictError(MoneyOSError):
    """A requested mutation conflicts with existing state."""


class DatabaseNotInitializedError(MoneyOSError):
    """The target is not an initialized MoneyOS database."""
