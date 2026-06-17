from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.core.config import Settings, settings
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.integrations.zoom.auth import ZoomOAuthClient
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
    """Small Zoom REST API wrapper for future metadata/download calls."""

    def __init__(
        self,
        oauth_client: ZoomOAuthClient | None = None,
        config: Settings = settings,
    ) -> None:
        self.config = config
        self.oauth_client = oauth_client or ZoomOAuthClient(config)

    def get(self, path: str, *, params: dict | None = None) -> dict:
        token = self.oauth_client.get_access_token()
        url = f"{self.config.zoom_api_base_url.rstrip('/')}/{path.lstrip('/')}"

        def send_request() -> httpx.Response:
            return httpx.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token.access_token}"},
                timeout=self.config.zoom_oauth_timeout_seconds,
            )

        try:
            response = retry_sync(
                send_request,
                attempts=self.config.zoom_oauth_retry_attempts,
                backoff_seconds=self.config.zoom_oauth_retry_backoff_seconds,
                retry_on_status={429, 500, 502, 503, 504},
            )
            if response.status_code == 401:
                token = self.oauth_client.get_access_token(force_refresh=True)
                response = httpx.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {token.access_token}"},
                    timeout=self.config.zoom_oauth_timeout_seconds,
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("zoom_api.request_failed", extra={"path": path})
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
            timeout=httpx.Timeout(self.config.zoom_oauth_timeout_seconds, read=None),
        )
        request = client.build_request(
            "GET",
            url,
            headers={"Authorization": f"Bearer {token.access_token}"},
        )
        response = client.send(request, stream=True)
        return ZoomDownloadResponse(response=response, client=client)
