"""Problems we can explain in one calm sentence."""


class UserError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
