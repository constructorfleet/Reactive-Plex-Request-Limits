from datetime import UTC, datetime
from types import SimpleNamespace

from request_shock.clients import (
    OverseerrClient,
    TautulliClient,
    _external_ids,
    _get,
    _guid_ids,
    _model_dict,
    _parse_datetime,
    _season_number,
    _to_request,
    _to_watch,
)
from request_shock.config import load_config
from request_shock.policy import Limits
from request_shock.state import load_state, save_state, updated_entry


def test_load_config_builds_nested_policy(tmp_path):
    config = tmp_path / "config.yml"
    config.write_text(
        """
overseerr:
  url: http://overseerr
  api_key: abc
tautulli:
  url: http://tautulli
  api_key: def
policy:
  normal_limits:
    movie_limit: 6
    movie_days: 3
    tv_limit: 2
    tv_days: 7
  recovery_per_run: 2
""",
        encoding="utf-8",
    )

    raw, policy = load_config(config)

    assert raw["overseerr"]["url"] == "http://overseerr"
    assert policy.normal_limits.movie_limit == 6
    assert policy.recovery_per_run == 2


def test_state_roundtrip(tmp_path):
    path = tmp_path / "nested" / "state.json"

    assert load_state(path) == {}

    state = {"7": updated_entry(3, "penalized")}
    save_state(path, state)

    loaded = load_state(path)
    assert loaded["7"].score == 3
    assert loaded["7"].last_reason == "penalized"
    assert loaded["7"].updated_at is not None


def test_client_helpers_handle_dicts_models_and_dates():
    model = SimpleNamespace(
        value="direct",
        additional_properties={"fallbackValue": "camel", "fallback_value": "snake"},
    )

    assert _get({"fallbackValue": "dict"}, "fallback_value") == "dict"
    assert _get(model, "value") == "direct"
    assert _get(model, "fallback_value") == "snake"
    assert _get(None, "missing", "default") == "default"
    assert _external_ids({"tmdbId": 123, "tvdb_id": 456}) == {"tmdb": "123", "tvdb": "456"}
    assert _guid_ids("plex://x tmdb://123 tvdb://456/7 imdb://tt789") == {
        "tmdb": "123",
        "tvdb": "456",
        "imdb": "tt789",
    }
    assert _season_number([{"seasonNumber": 2}]) == 2
    assert _season_number([]) is None
    assert _parse_datetime(0) == datetime(1970, 1, 1, tzinfo=UTC)
    assert _parse_datetime("2026-05-07T00:00:00Z") == datetime(2026, 5, 7, tzinfo=UTC)


def test_model_dict_flattens_additional_properties():
    model = SimpleNamespace(
        model_dump=lambda by_alias, exclude_none: {
            "username": "Taylor",
            "additionalProperties": {"movieQuotaLimit": 5},
            "additional_properties": {"tvQuotaLimit": 1},
        }
    )

    assert _model_dict(model) == {
        "username": "Taylor",
        "movieQuotaLimit": 5,
        "tvQuotaLimit": 1,
    }
    assert _model_dict({"username": "Taylor"}) == {"username": "Taylor"}


def test_to_request_maps_overseerr_payload():
    item = {
        "id": 42,
        "createdAt": "2026-05-01T00:00:00Z",
        "requestedBy": {"id": 7},
        "media": {"title": "Movie", "mediaType": "movie", "tmdbId": 123},
    }

    request = _to_request(item, fallback_user_id=99)

    assert request.request_id == 42
    assert request.user_id == 7
    assert request.media_type == "movie"
    assert request.external_ids == {"tmdb": "123"}


def test_to_request_infers_tv_payload_with_season():
    item = {
        "id": 43,
        "createdAt": "2026-05-01T00:00:00Z",
        "media": {"name": "Show", "tvdbId": 456, "episodeCount": 10},
        "seasons": [{"seasonNumber": 1}],
    }

    request = _to_request(item, fallback_user_id=7)

    assert request.media_type == "tv"
    assert request.title == "Show"
    assert request.season_number == 1
    assert request.episode_count == 10


def test_to_watch_maps_tautulli_movie_and_episode_payloads():
    movie = _to_watch(
        {
            "user_id": 7,
            "media_type": "movie",
            "title": "Movie",
            "date": 0,
            "duration": 100,
            "view_offset": 80,
            "guid": "tmdb://123",
        }
    )
    episode = _to_watch(
        {
            "user_id": 7,
            "media_type": "episode",
            "grandparent_title": "Show",
            "date": "2026-05-07T00:00:00Z",
            "parent_media_index": "2",
            "media_index": "3",
        }
    )

    assert movie.percent_complete == 0.8
    assert movie.external_ids == {"tmdb": "123"}
    assert episode.title == "Show"
    assert episode.season_number == 2
    assert episode.episode_number == 3


def test_overseerr_client_wraps_library(monkeypatch):
    calls = {}

    class FakeApiClient:
        def __init__(self, config):
            self.config = config
            calls["host"] = config.host

        def close(self):
            calls["closed"] = True

    class FakeUsersApi:
        def __init__(self, api_client):
            self.api_client = api_client

        def get_user(self, take, skip):
            return SimpleNamespace(results=[SimpleNamespace(id=7)])

        def get_user_requests(self, user_id, take, skip):
            return SimpleNamespace(results=[])

        def get_user_settings_main(self, user_id):
            return {"username": "Taylor"}

        def create_user_settings_main(self, user_id, create_user_settings_main_request):
            calls["update"] = (user_id, create_user_settings_main_request)

    monkeypatch.setattr("request_shock.clients.overseerr.ApiClient", FakeApiClient)
    monkeypatch.setattr("request_shock.clients.overseerr.UsersApi", FakeUsersApi)

    client = OverseerrClient("http://overseerr", "key")

    assert calls["host"] == "http://overseerr/api/v1"
    assert client.list_users()[0].id == 7
    assert client.list_requests(7) == []
    assert client.get_user_settings(7) == {"username": "Taylor"}

    client.set_limits(7, Limits(1, 2, 3, 4), {"username": "Taylor"})
    assert calls["update"][0] == 7

    client.close()
    assert calls["closed"]


def test_tautulli_client_wraps_raw_api(monkeypatch):
    calls = {}

    class FakeRawAPI:
        def __init__(self, base_url, api_key, ssl_verify, verify):
            calls["init"] = (base_url, api_key, ssl_verify, verify)

        def get_history(self, **kwargs):
            calls["history"] = kwargs
            return {"data": {"data": [{"user_id": 7, "media_type": "movie", "title": "Movie", "date": 0}]}}

        def notify(self, notifier_id, subject, body):
            calls["notify"] = (notifier_id, subject, body)

    monkeypatch.setattr("request_shock.clients.RawAPI", FakeRawAPI)

    client = TautulliClient("http://tautulli/", "key", verify_ssl=False)
    history = client.history_for_user(username="Taylor", length=25)
    client.notify(3, "Subject", "Body")

    assert calls["init"] == ("http://tautulli", "key", False, False)
    assert calls["history"]["user"] == "Taylor"
    assert calls["history"]["length"] == 25
    assert history[0].title == "Movie"
    assert calls["notify"] == (3, "Subject", "Body")
