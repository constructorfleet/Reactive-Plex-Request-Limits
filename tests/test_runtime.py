from dataclasses import dataclass

from request_shock.cli import (
    build_throttle_message,
    is_exempt_user,
    should_notify_throttle,
)
from request_shock.policy import Limits, PolicyConfig


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
