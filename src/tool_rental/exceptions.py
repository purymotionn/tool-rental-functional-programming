class RentalError(Exception):
    pass


class ValidationError(RentalError):
    pass


class EntityNotFoundError(RentalError):
    pass


class InvalidStateError(RentalError):
    pass


class ToolUnavailableError(RentalError):
    pass


class InsufficientDepositError(RentalError):
    pass
