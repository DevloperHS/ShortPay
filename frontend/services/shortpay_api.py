from typing import Any

import requests


class ShortpayAPIError(RuntimeError):
    """A safe, user-facing FastAPI communication error."""


class ShortpayAPI:
    def __init__(self, base_url: str, timeout: float = 15, session=None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout,
                **kwargs,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            detail = "FastAPI is unavailable. Start the backend and try again."
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    detail = response.json().get("detail", detail)
                except ValueError:
                    pass
            raise ShortpayAPIError(detail) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ShortpayAPIError("FastAPI returned an invalid response.") from exc

    def list_cases(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/cases")

    def get_case(self, invoice_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/cases/{invoice_id}")

    def ingest_invoice(self, invoice_text: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/ingest/invoice",
            json={"raw_invoice_text": invoice_text, "auto_match": True},
        )

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/decide", json=payload)
