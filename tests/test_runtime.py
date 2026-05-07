import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from request_shock import cli
from request_shock.cli import (
    build_throttle_message,
    is_exempt_user,
    main,
    should_notify_throttle,
)
from request_shock.policy import Limits, PolicyConfig, Request


@dataclass
class FakeUser:
    id: int
    username: str | None = None
    plex_username: str | None = None
    email: str | None = None


def test_exempt_user_can_be_matched_by_id_username_plex_username_or_email():
    config = {
        "ignore_user_ids": [9],
        "exempt_users": {
            "ids": [10],
            "usernames": ["local_user"],
            "plex_usernames": ["PlexUser"],
            "emails": ["friend@example.com"],
        },
    }

    assert is_exempt_user(FakeUser(id=9), config)
    assert is_exempt_user(FakeUser(id=10), config)
    assert is_exempt_user(FakeUser(id=11, username="LOCAL_USER"), config)
    assert is_exempt_user(FakeUser(id=12, plex_username="plexuser"), config)
    assert is_exempt_user(FakeUser(id=13, email="FRIEND@example.com"), config)
    assert not is_exempt_user(FakeUser(id=14, username="other"), config)


def test_notify_throttle_only_when_moving_to_stricter_limits():
    config = PolicyConfig(
        normal_limits=Limits(5, 3, 1, 7),
        warning_limits=Limits(3, 7, 1, 14),
        restricted_limits=Limits(1, 14, 1, 30),
        warning_score=1,
        restricted_score=3,
    )

    assert should_notify_throttle(prior_score=0, new_score=1, config=config)
    assert should_notify_throttle(prior_score=2, new_score=3, config=config)
    assert not should_notify_throttle(prior_score=1, new_score=2, config=config)
    assert not should_notify_throttle(prior_score=3, new_score=2, config=config)


def test_build_throttle_message_uses_configured_template():
    subject, body = build_throttle_message(
        username="Taylor",
        score=3,
        limits=Limits(movie_limit=1, movie_days=14, tv_limit=1, tv_days=30),
        notification_config={
            "subject": "Request limits updated for {username}",
            "body": "Ah ah ah, {username}. Movies: {movie_limit}/{movie_days} days. TV: {tv_limit}/{tv_days} days.",
        },
    )

    assert subject == "Request limits updated for Taylor"
    assert body == "Ah ah ah, Taylor. Movies: 1/14 days. TV: 1/30 days."


def test_main_dry_run_skips_exempt_and_reports_notification(monkeypatch, tmp_path, capsys):
    config = tmp_path / "config.yml"
    state = tmp_path / "state.json"
    config.write_text(
        """
overseerr:
  url: http://overseerr
  api_key: overseerr-key
tautulli:
  url: http://tautulli
  api_key: tautulli-key
  history_length: 25
ignore_user_ids:
  - 1
notifications:
  tautulli_notifier_ids:
    - 3
policy:
  movie_grace_days: 1
""",
        encoding="utf-8",
    )

    class FakeOverseerrClient:
        def __init__(self, url, api_key):
            self.url = url
            self.api_key = api_key

        def list_users(self):
            return [
                FakeUser(id=1, username="admin"),
                FakeUser(id=2),
                FakeUser(id=7, username="Taylor"),
            ]

        def list_requests(self, user_id):
            return [
                Request(
                    request_id=42,
                    user_id=user_id,
                    media_type="movie",
                    title="Movie",
                    created_at=datetime.now(UTC) - timedelta(days=10),
                )
            ]

        def get_user_settings(self, user_id):
            return {
                "username": "Taylor",
                "movieQuotaLimit": 5,
                "movieQuotaDays": 3,
                "tvQuotaLimit": 1,
                "tvQuotaDays": 7,
            }

        def set_limits(self, user_id, limits, settings):
            raise AssertionError("dry run must not write limits")

        def close(self):
            pass

    class FakeTautulliClient:
        def __init__(self, url, api_key, verify_ssl=True):
            pass

        def history_for_user(self, username, length):
            return []

        def notify(self, notifier_id, subject, body):
            raise AssertionError("dry run must not send notifications")

    monkeypatch.setattr(cli, "OverseerrClient", FakeOverseerrClient)
    monkeypatch.setattr(cli, "TautulliClient", FakeTautulliClient)
    monkeypatch.setattr(
        sys,
        "argv",
        ["request-shock", "--config", str(config), "--state", str(state), "--dry-run"],
    )

    assert main() == 0

    output = capsys.readouterr().out
    assert "skip user=admin: exempt" in output
    assert "skip user 2: no username available" in output
    assert "dry run: would notify user=Taylor" in output
    assert not state.exists()


def test_main_applies_limits_saves_state_and_notifies(monkeypatch, tmp_path):
    config = tmp_path / "config.yml"
    state = tmp_path / "state.json"
    calls = {"limits": [], "notifications": []}
    config.write_text(
        """
overseerr:
  url: http://overseerr
  api_key: overseerr-key
tautulli:
  url: http://tautulli
  api_key: tautulli-key
notifications:
  tautulli_notifier_ids:
    - 3
policy:
  movie_grace_days: 1
""",
        encoding="utf-8",
    )

    class FakeOverseerrClient:
        def __init__(self, url, api_key):
            pass

        def list_users(self):
            return [FakeUser(id=7, username="Taylor")]

        def list_requests(self, user_id):
            return [
                Request(
                    request_id=42,
                    user_id=user_id,
                    media_type="movie",
                    title="Movie",
                    created_at=datetime.now(UTC) - timedelta(days=10),
                )
            ]

        def get_user_settings(self, user_id):
            return {
                "username": "Taylor",
                "movieQuotaLimit": 5,
                "movieQuotaDays": 3,
                "tvQuotaLimit": 1,
                "tvQuotaDays": 7,
            }

        def set_limits(self, user_id, limits, settings):
            calls["limits"].append((user_id, limits))

        def close(self):
            calls["closed"] = True

    class FakeTautulliClient:
        def __init__(self, url, api_key, verify_ssl=True):
            pass

        def history_for_user(self, username, length):
            return []

        def notify(self, notifier_id, subject, body):
            calls["notifications"].append((notifier_id, subject, body))

    monkeypatch.setattr(cli, "OverseerrClient", FakeOverseerrClient)
    monkeypatch.setattr(cli, "TautulliClient", FakeTautulliClient)
    monkeypatch.setattr(sys, "argv", ["request-shock", "--config", str(config), "--state", str(state)])

    assert main() == 0

    assert calls["limits"][0][0] == 7
    assert calls["limits"][0][1].movie_limit == 3
    assert calls["notifications"][0][0] == 3
    assert state.exists()
    assert calls["closed"]
