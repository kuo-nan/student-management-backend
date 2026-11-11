from collections.abc import Mapping

from fastapi import HTTPException


class BusinessHTTPException(HTTPException):
    """携带明确业务码的 HTTP 异常。"""

    def __init__(
        self,
        *,
        status_code: int,
        code: int,
        detail: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
