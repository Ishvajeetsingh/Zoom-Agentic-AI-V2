import base64
import time
from dataclasses import dataclass

import httpx

from app.core.errors import ConfigurationError, ExternalServiceError
from app.core.logging import get_logger
from app.integrations.zoom.retry import retry_sync

logger = get_logger(__name__)


@dataclass(frozen=True)
class ZoomAccessToken:
    access_token: str
    token_type: str
    expires_in: int
    expires_at: float
    scope: str | None = None
    api_url: str | None = None


class ZoomOAuthClient:
    def __init__(self, account_id: str, client_id: str, client_secret: str, token_url: str = "https://zoom.us/oauth/token", timeout: float = 10.0, retry_attempts: int = 3, retry_backoff: float = 1.0) -> None:
        self._account_id = account_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._timeout = timeout
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff
        self._cached_token: ZoomAccessToken | None = None

    def get_access_token(self, *, force_refresh: bool = False) -> ZoomAccessToken:
        if not force_refresh and self._cached_token and self._cached_token.expires_at > time.time() + 60:
            return self._cached_token

        self._cached_token = self._request_access_token()
        return self._cached_token

    def _request_access_token(self) -> ZoomAccessToken:
        if not self._account_id or not self._client_id or not self._client_secret:
            raise ConfigurationError("Missing required Zoom OAuth settings for account")

        auth_header = self._basic_authorization_header()
        data = {
            "grant_type": "account_credentials",
            "account_id": self._account_id,
        }

        def send_request() -> httpx.Response:
            return httpx.post(
                self._token_url,
                data=data,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self._timeout,
            )

        try:
            response = retry_sync(
                send_request,
                attempts=self._retry_attempts,
                backoff_seconds=self._retry_backoff,
                retry_on_status={429, 500, 502, 503, 504},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("zoom_oauth.token_request_failed")
            raise ExternalServiceError("Failed to generate Zoom access token") from exc

        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise ExternalServiceError("Zoom access token response did not include access_token")

        expires_in = int(payload.get("expires_in", 3600))
        token = ZoomAccessToken(
            access_token=access_token,
            token_type=payload.get("token_type", "bearer"),
            expires_in=expires_in,
            expires_at=time.time() + expires_in,
            scope=payload.get("scope"),
            api_url=payload.get("api_url"),
        )
        logger.info(
            "zoom_oauth.token_generated",
            extra={"expires_in": token.expires_in, "scope": token.scope, "account_id": self._account_id},
        )
        return token

    def _basic_authorization_header(self) -> str:
        raw_credentials = f"{self._client_id}:{self._client_secret}".encode()
        encoded = base64.b64encode(raw_credentials).decode("ascii")
        return f"Basic {encoded}"


_zoom_oauth_cache: dict[str, ZoomOAuthClient] = {}


def get_oauth_client_for_account(
    account_id: str,
    client_id: str,
    client_secret: str,
    token_url: str = "https://zoom.us/oauth/token",
    timeout: float = 10.0,
    retry_attempts: int = 3,
    retry_backoff: float = 1.0,
) -> ZoomOAuthClient:
    cache_key = account_id
    cached = _zoom_oauth_cache.get(cache_key)
    if cached is not None:
        if (
            cached._account_id == account_id
            and cached._client_id == client_id
            and cached._client_secret == client_secret
        ):
            return cached

    client = ZoomOAuthClient(
        account_id=account_id,
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
    )
    _zoom_oauth_cache[cache_key] = client
    return client


def clear_oauth_cache() -> None:
    _zoom_oauth_cache.clear()
