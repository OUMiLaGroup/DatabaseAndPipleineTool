"""Safe customer-facing messages; never serialize request headers or signed URLs."""
import httpx


class MissingRouteRecordingsError(ValueError):
    pass


def describe_download_failure(error: Exception) -> dict[str, str]:
    if isinstance(error, MissingRouteRecordingsError):
        return {'code': 'recordings_unavailable', 'message': 'Comma has route metadata but no complete downloadable road-camera, wide-camera and log recordings. Ask your project contact to upload the recordings or provide another route.'}
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 401:
            return {'code': 'authentication_failed', 'message': 'Comma rejected your token. Obtain a fresh JWT from jwt.comma.ai, update COMMA_JWT in your account configuration, and restart the application services.'}
        if status == 403:
            return {'code': 'access_denied', 'message': 'Your Comma account does not have access to this route. Ask the device owner to grant access or use an authorized account.'}
        if status == 404:
            return {'code': 'route_not_found', 'message': 'Comma could not find this route. Check the route ID and confirm the recordings are available.'}
        return {'code': 'comma_service_error', 'message': 'Comma could not complete the request. Try again later; if it continues, ask your project contact to check the Comma service.'}
    if isinstance(error, (httpx.RequestError, TimeoutError)):
        return {'code': 'connection_failed', 'message': 'The download timed out or could not connect. Check your internet connection and retry.'}
    return {'code': 'processing_failed', 'message': 'Replay or frame extraction failed. Check the download-worker logs for details, then retry. Contact your project team if the error continues.'}
