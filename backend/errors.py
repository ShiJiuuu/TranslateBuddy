class TranslateBuddyError(Exception):
    code = "E_UNKNOWN"

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.detail = detail or {}


class UnsupportedFormat(TranslateBuddyError):
    code = "E_UNSUPPORTED_FORMAT"


class MissingConverter(TranslateBuddyError):
    code = "E_NO_CONVERTER"


class FileTooLarge(TranslateBuddyError):
    code = "E_TOO_LARGE"


class TranslationFailed(TranslateBuddyError):
    code = "E_TRANSLATION_FAILED"
