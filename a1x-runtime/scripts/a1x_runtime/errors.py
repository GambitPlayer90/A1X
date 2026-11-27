class A1XError(Exception):
    """Expected, user-actionable runtime error."""


class IntegrityError(A1XError):
    """An immutable artifact or declared input no longer matches."""


class ValidationError(A1XError):
    """A supplied record is structurally invalid."""


class BudgetError(A1XError):
    """A configured campaign budget would be exceeded."""


class StateTransitionError(A1XError):
    """An event-sourced record was asked to make an invalid transition."""
