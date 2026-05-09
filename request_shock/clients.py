from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import overseerr
import requests

from request_shock.policy import Limits, Request, Watch


class OverseerrClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        host = base_url.rstrip("/")
        if not host.endswith("/api/v1"):
            host = f"{host}/api/v1"
        config = overseerr.Configuration(host=host, api_key={"apiKey": api_key})
        self._api_client = overseerr.ApiClient(config)
        self._users = overseerr.UsersApi(self._api_client)

    def close(self) -> None:
        self._api_client.close()

    def list_users(self) -> list[Any]:
        response = self._users.get_user(take=1000, skip=0)
        return list(_get(response, "results", []))

    def list_requests(self, user_id: int) -> list[Request]:
        response = self._users.get_user_requests(user_id=user_id, take=1000, skip=0)
        return [_to_request(item, user_id) for item in _get(response, "results", [])]

    def get_user_settings(self, user_id: int) -> dict[str, Any]:
        settings = self._users.get_user_settings_main(user_id=user_id)
        return _model_dict(settings)

    def set_limits(self, user_id: int, limits: Limits, existing_settings: dict[str, Any]) -> None:
        payload = dict(existing_settings)
        payload.update(
            {
                "movieQuotaLimit": limits.movie_limit,
                "movieQuotaDays": limits.movie_days,
                "tvQuotaLimit": limits.tv_limit,
                "tvQuotaDays": limits.tv_days,
            }
        )
        username = payload.pop("username", None)
        request = overseerr.CreateUserSettingsMainRequest(username=username, additional_properties=payload)
        self._users.create_user_settings_main(user_id=user_id, create_user_settings_main_request=request)


class TautulliClient:
    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = True) -> None:
        self._base_url = f"{base_url.rstrip('/')}/api/v2"
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._session = requests.Session()

    def history_for_user(
        self, username: str | None = None, user_id: int | None = None, length: int = 1000
    ) -> list[Watch]:
        data = self._get(
            {
                "cmd": "get_history",
                "grouping": True,
                "user": username,
                "user_id": user_id,
                "media_type": "movie,episode",
                "order_column": "date",
                "order_direction": "desc",
                "start": 0,
                "length": length,
            }
        )
        rows = data.get("data", data)
        if isinstance(rows, dict):
            rows = rows.get("data", [])
        return [_to_watch(row) for row in rows]

    def notify(self, notifier_id: int, subject: str, body: str) -> None:
        self._get(
            {
                "cmd": "notify",
                "notifier_id": notifier_id,
                "subject": subject,
                "body": body,
            }
        )

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        request_params = {"apikey": self._api_key, **{key: value for key, value in params.items() if value is not None}}
        response = self._session.get(self._base_url, params=request_params, timeout=30, verify=self._verify_ssl)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("response"), dict):
            return payload["response"]
        return payload


def _to_request(item: Any, fallback_user_id: int) -> Request:
    media = _get(item, "media", None)
    requested_by = _get(item, "requested_by", None)
    user_id = int(_get(requested_by, "id", fallback_user_id) or fallback_user_id)
    title = _first_present(item, media, keys=("title", "name", "original_title", "original_name")) or "Unknown"
    media_type = (_first_present(item, media, keys=("media_type", "mediaType", "type")) or "").lower()
    if media_type not in {"movie", "tv"}:
        media_type = "movie" if _get(media, "tmdb_id", None) and not _get(media, "tvdb_id", None) else "tv"
    seasons = _get(item, "seasons", []) or _get(item, "additional_properties", {}).get("seasons", [])
    season_number = _season_number(seasons)
    episode_count = _first_present(item, media, keys=("episode_count", "episodeCount", "number_of_episodes"))
    return Request(
        request_id=int(_get(item, "id", 0)),
        user_id=user_id,
        media_type=media_type,
        title=str(title),
        created_at=_parse_datetime(_get(item, "created_at", None)),
        season_number=season_number,
        episode_count=int(episode_count) if episode_count else None,
        external_ids=_external_ids(media),
    )


def _to_watch(row: dict[str, Any]) -> Watch:
    media_type = str(row.get("media_type") or row.get("type") or "").lower()
    title = row.get("grandparent_title") or row.get("title") or row.get("full_title") or "Unknown"
    if media_type == "movie":
        title = row.get("title") or title
    watched_at = _parse_datetime(row.get("date") or row.get("watched_at") or row.get("started"))
    percent = row.get("percent_complete")
    if percent is None and row.get("duration") and row.get("view_offset"):
        percent = float(row["view_offset"]) / float(row["duration"])
    return Watch(
        user_id=int(row.get("user_id") or row.get("user_id_num") or 0),
        media_type=media_type,
        title=str(title),
        watched_at=watched_at,
        season_number=_int_or_none(row.get("parent_media_index")),
        episode_number=_int_or_none(row.get("media_index")),
        percent_complete=float(percent) if percent is not None else None,
        external_ids=_guid_ids(row.get("guid") or row.get("guids") or ""),
    )


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, obj.get(_camel(key), default))
    if hasattr(obj, key):
        return getattr(obj, key)
    additional = getattr(obj, "additional_properties", None)
    if isinstance(additional, dict):
        return additional.get(key, additional.get(_camel(key), default))
    return default


def _model_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(by_alias=True, exclude_none=True)
        data.update(data.pop("additionalProperties", {}) or {})
        data.update(data.pop("additional_properties", {}) or {})
        return data
    return dict(obj)


def _first_present(*objects: Any, keys: tuple[str, ...]) -> Any:
    for obj in objects:
        for key in keys:
            value = _get(obj, key, None)
            if value not in (None, ""):
                return value
    return None


def _external_ids(media: Any) -> dict[str, str]:
    ids: dict[str, str] = {}
    for source, key in (("tmdb", "tmdb_id"), ("tvdb", "tvdb_id"), ("imdb", "imdb_id")):
        value = _get(media, key, None)
        if value:
            ids[source] = str(value)
    return ids


def _guid_ids(value: Any) -> dict[str, str]:
    text = " ".join(value) if isinstance(value, list) else str(value)
    ids: dict[str, str] = {}
    for source in ("tmdb", "tvdb", "imdb"):
        marker = f"{source}://"
        if marker in text:
            ids[source] = text.split(marker, 1)[1].split()[0].split("/")[0]
    return ids


def _season_number(seasons: Any) -> int | None:
    if isinstance(seasons, list) and len(seasons) == 1:
        return _int_or_none(_get(seasons[0], "season_number", _get(seasons[0], "seasonNumber", None)))
    return None


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(UTC)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)
