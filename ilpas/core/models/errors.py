class IlpasError(Exception):
    """Base class for exceptions in this module."""

    pass


class IlpasValueError(IlpasError, ValueError):
    """Exception raised for errors in the input."""

    pass


class NotFoundException(IlpasError):
    """Exception raised when a requested key is not found."""

    pass


class ConflictException(IlpasError):
    """Exception raised when there's a conflict in the data."""

    pass
