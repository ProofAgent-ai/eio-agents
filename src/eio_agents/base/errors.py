"""The library's error type. Every failure fails closed (03 PROD-3): an exception means no record."""


class ConversionError(Exception):
    """Fail closed (03 PROD-3): any exception means no record. `code` is the typed error code (a neutral token such as
    `BUNDLE_SCHEMA`, never an EIO id), or None for an error raised without one."""

    def __init__(self, message="", code=None):
        super().__init__(message)
        self.code = code


def require(cond, code, detail=""):
    if not cond:
        raise ConversionError(f"{code}: {detail}", code=code)
