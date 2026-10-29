import os
import time
from typing import Any

import httpx
from utilities.download_errors import MissingRouteRecordingsError

from schemas.openpilot_route_metadata import OpenPilotRouteMetadata
from services.errors import CommaApiError, CommaAuthError, InvalidRouteIdError
from utilities.open_pilot_utilities import get_open_pilot_device_name_from_route_str, is_valid_route_str


class OpenPilotRouteService:
    def __init__(self) -> None:
        self.jwt_token = os.environ["COMMA_JWT"]
        self.auth_headers = {"Authorization": f"JWT {self.jwt_token}"}

    async def get_route_metadata(
        self,
        route_name: str,
    ) -> OpenPilotRouteMetadata | None:
        if not is_valid_route_str(route_name):
            raise InvalidRouteIdError(route_name)

        dongle_id = get_open_pilot_device_name_from_route_str(route_name)
        timeout = httpx.Timeout(10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(
                    url=f"https://api.commadotai.com/v1/devices/{dongle_id}/routes_segments",
                    headers=self.auth_headers,
                    params={
                        "start": 0,
                        "end": int(time.time() * 1000),  # epoch time in ms
                    },
                )
        except httpx.HTTPError as e:
            raise CommaApiError(f"Could not reach the comma.ai API: {type(e).__name__}: {e}", dongle_id) from e

        # Translate HTTP errors into messages that say what to do
        # comma answers 404 both for unknown devices and devices the token can't see
        if resp.status_code in (401, 403, 404):
            raise CommaAuthError(dongle_id=dongle_id, http_status=resp.status_code)
        if resp.status_code >= 400:
            raise CommaApiError(
                f"comma.ai API returned HTTP {resp.status_code} for device {dongle_id}: {resp.text[:200]}",
                dongle_id,
            )
        response_json: list[Any] = resp.json()

        for raw_route in response_json:
            route_metadata = OpenPilotRouteMetadata.model_validate(raw_route)
            if route_metadata.fullname == route_name:
                return route_metadata

        return None

    async def require_downloadable_files(self, route_name: str) -> None:
        """Metadata can outlive uploaded recordings. Check before starting replay."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"https://api.commadotai.com/v1/route/{route_name}/files",
                headers=self.auth_headers,
            )
            response.raise_for_status()
            files = response.json()
        if not files.get('logs') or not files.get('cameras') or not files.get('ecameras'):
            raise MissingRouteRecordingsError(
                f"Route {route_name} has no complete downloadable road/wide camera and rlog files. "
                "Comma route metadata alone does not mean its recordings are available."
            )
