from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

import httpx

from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.integrations.zoom.auth_multi import ZoomOAuthClient
from app.integrations.zoom.retry import retry_sync

logger = get_logger(__name__)


@dataclass
class ZoomDownloadResponse:
    response: httpx.Response
    client: httpx.Client

    @property
    def status_code(self) -> int:
        return self.response.status_code

    def raise_for_status(self) -> None:
        self.response.raise_for_status()

    def iter_bytes(self):
        return self.response.iter_bytes()

    def close(self) -> None:
        self.response.close()
        self.client.close()


class ZoomApiClient:
    def __init__(
        self,
        oauth_client: ZoomOAuthClient,
        api_base_url: str = "https://api.zoom.us/v2",
        timeout: float = 10.0,
        retry_attempts: int = 3,
        retry_backoff: float = 1.0,
    ) -> None:
        self.api_base_url = api_base_url
        self.oauth_client = oauth_client
        self._timeout = timeout
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff

    def get(self, path: str, *, params: dict | None = None) -> dict:
        token = self.oauth_client.get_access_token()
        url = f"{self.api_base_url.rstrip('/')}/{path.lstrip('/')}"

        def send_request() -> httpx.Response:
            return httpx.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token.access_token}"},
                timeout=self._timeout,
            )

        try:
            response = retry_sync(
                send_request,
                attempts=self._retry_attempts,
                backoff_seconds=self._retry_backoff,
                retry_on_status={429, 500, 502, 503, 504},
            )
            if response.status_code == 401:
                token = self.oauth_client.get_access_token(force_refresh=True)
                response = httpx.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token.access_token}"},
                    timeout=self._timeout,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            response_body = ""
            status_code = None
            request_url = str(exc.request.url) if exc.request else url
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
                try:
                    response_body = exc.response.text
                except Exception:
                    response_body = "<unreadable>"
            logger.exception(
                "zoom_api.request_failed",
                extra={
                    "path": path,
                    "request_url": request_url,
                    "status_code": status_code,
                    "response_body": response_body,
                },
            )
            raise ExternalServiceError(f"Zoom API request failed for {path}") from exc

        return response.json()

    def get_recording_metadata(self, meeting_uuid: str) -> dict:
        encoded_uuid = quote(quote(meeting_uuid, safe=""), safe="")
        return self.get(f"/meetings/{encoded_uuid}/recordings")

    def list_user_recordings(
        self,
        *,
        user_id: str = "me",
        from_date: str | None = None,
        to_date: str | None = None,
        page_size: int = 300,
        next_page_token: str | None = None,
    ) -> dict:
        params: dict[str, object] = {"page_size": min(page_size, 300)}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if next_page_token:
            params["next_page_token"] = next_page_token
        return self.get(f"/users/{user_id}/recordings", params=params)

    def get_meeting_recordings(self, meeting_id: str) -> dict:
        encoded_id = quote(quote(meeting_id, safe=""), safe="")
        return self.get(f"/meetings/{encoded_id}/recordings")

    def stream_download(self, url: str, *, force_refresh_token: bool = False) -> ZoomDownloadResponse:
        token = self.oauth_client.get_access_token(force_refresh=force_refresh_token)
        client = httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(self._timeout, read=None),
        )
        request = client.build_request(
            "GET",
            url,
            headers={"Authorization": f"Bearer {token.access_token}"},
        )
        response = client.send(request, stream=True)
        return ZoomDownloadResponse(response=response, client=client)


_zoom_api_cache: dict[str, ZoomApiClient] = {}


def get_zoom_api_client(
    account_id: str,
    client_id: str,
    client_secret: str,
    token_url: str = "https://zoom.us/oauth/token",
    api_base_url: str = "https://api.zoom.us/v2",
    timeout: float = 10.0,
    retry_attempts: int = 3,
    retry_backoff: float = 1.0,
) -> ZoomApiClient:
    from app.integrations.zoom.auth_multi import get_oauth_client_for_account

    cache_key = f"{account_id}:{client_id}:{api_base_url}"
    cached = _zoom_api_cache.get(cache_key)
    if cached is not None:
        return cached

    oauth_client = get_oauth_client_for_account(
        account_id=account_id,
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
    )
    api_client = ZoomApiClient(
        oauth_client=oauth_client,
        api_base_url=api_base_url,
        timeout=timeout,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
    )
    _zoom_api_cache[cache_key] = api_client
    return api_client


def get_zoom_api_client_from_db(db, zoom_account_id: UUID) -> ZoomApiClient:
    from app.db.repositories import zoom_accounts as zoom_account_repo

    account = zoom_account_repo.get_by_id(db, zoom_account_id)
    if account is None:
        raise ExternalServiceError(f"Zoom account not found: {zoom_account_id}")
    if not account.enabled:
        raise ExternalServiceError(f"Zoom account is disabled: {account.account_name}")

    return get_zoom_api_client(
        account_id=account.zoom_account_id,
        client_id=account.client_id,
        client_secret=account.client_secret,
        token_url=account.token_url,
        api_base_url=account.api_base_url,
    )


def get_default_zoom_api_client(db) -> ZoomApiClient | None:
    from app.db.repositories import zoom_accounts as zoom_account_repo

    account = zoom_account_repo.get_default(db)
    if account is None:
        return None
    if not account.enabled:
        return None

    return get_zoom_api_client(
        account_id=account.zoom_account_id,
        client_id=account.client_id,
        client_secret=account.client_secret,
        token_url=account.token_url,
        api_base_url=account.api_base_url,
    )


def get_legacy_zoom_api_client() -> ZoomApiClient:
    from app.core.config import settings

    return get_zoom_api_client(
        account_id=settings.zoom_account_id or "",
        client_id=settings.zoom_client_id or "",
        client_secret=settings.zoom_client_secret or "",
        token_url=settings.zoom_token_url,
        api_base_url=settings.zoom_api_base_url,
        timeout=settings.zoom_oauth_timeout_seconds,
        retry_attempts=settings.zoom_oauth_retry_attempts,
        retry_backoff=settings.zoom_oauth_retry_backoff_seconds,
    )


def clear_api_cache() -> None:
    from app.integrations.zoom.auth_multi import clear_oauth_cache
    _zoom_api_cache.clear()
    clear_oauth_cache()
