from datetime import UTC, datetime, timedelta

from request_shock.policy import (
    Limits,
    PolicyConfig,
    Request,
    StateEntry,
    Watch,
    evaluate_user,
)

NOW = datetime(2026, 5, 7, tzinfo=UTC)


def days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


def test_recent_requests_are_not_penalized_during_grace_period():
    config = PolicyConfig(movie_grace_days=14, tv_grace_days=21)
    request = Request(
        request_id=1,
        user_id=7,
        media_type="movie",
        title="Late Night Movie",
        created_at=days_ago(4),
    )

    result = evaluate_user(
        user_id=7,
        requests=[request],
        watches=[],
        prior_state=StateEntry(score=2),
        config=config,
        now=NOW,
    )

    assert result.score == 1
    assert result.reason == "recovered"


def test_unwatched_mature_movie_increases_score_and_reduces_limits():
    config = PolicyConfig(
        movie_grace_days=14,
        restricted_score=3,
        warning_limits=Limits(movie_limit=3, movie_days=7, tv_limit=1, tv_days=14),
    )
    request = Request(
        request_id=1,
        user_id=7,
        media_type="movie",
        title="Ignored Movie",
        created_at=days_ago(30),
    )

    result = evaluate_user(
        user_id=7,
        requests=[request],
        watches=[],
        prior_state=StateEntry(score=0),
        config=config,
        now=NOW,
    )

    assert result.score == 1
    assert result.reason == "penalized"
    assert result.limits.movie_limit == 3
    assert result.limits.movie_days == 7


def test_tv_season_with_non_trivial_watching_recovers_instead_of_penalizing():
    config = PolicyConfig(tv_grace_days=21, min_tv_fraction=0.2, min_tv_episodes=3)
    request = Request(
        request_id=2,
        user_id=7,
        media_type="tv",
        title="Pokemon",
        season_number=1,
        episode_count=70,
        created_at=days_ago(40),
    )
    watches = [
        Watch(
            user_id=7,
            media_type="episode",
            title="Pokemon",
            season_number=1,
            episode_number=episode,
            watched_at=days_ago(10),
        )
        for episode in range(1, 15)
    ]

    result = evaluate_user(
        user_id=7,
        requests=[request],
        watches=watches,
        prior_state=StateEntry(score=2),
        config=config,
        now=NOW,
    )

    assert result.score == 1
    assert result.reason == "recovered"


def test_tv_season_with_token_episode_watch_is_penalized():
    config = PolicyConfig(tv_grace_days=21, min_tv_fraction=0.2, min_tv_episodes=3)
    request = Request(
        request_id=2,
        user_id=7,
        media_type="tv",
        title="Pokemon",
        season_number=1,
        episode_count=70,
        created_at=days_ago(40),
    )
    watches = [
        Watch(
            user_id=7, media_type="episode", title="Pokemon", season_number=1, episode_number=1, watched_at=days_ago(10)
        )
    ]

    result = evaluate_user(
        user_id=7,
        requests=[request],
        watches=watches,
        prior_state=StateEntry(score=2),
        config=config,
        now=NOW,
    )

    assert result.score == 3
    assert result.limits.tv_limit == 1
    assert result.limits.tv_days == 30


def test_large_tv_season_requires_fraction_not_episode_floor():
    config = PolicyConfig(tv_grace_days=21, min_tv_fraction=0.2, min_tv_episodes=3)
    request = Request(
        request_id=2,
        user_id=7,
        media_type="tv",
        title="Pokemon",
        season_number=1,
        episode_count=70,
        created_at=days_ago(40),
    )
    watches = [
        Watch(
            user_id=7,
            media_type="episode",
            title="Pokemon",
            season_number=1,
            episode_number=episode,
            watched_at=days_ago(10),
        )
        for episode in range(1, 4)
    ]

    result = evaluate_user(
        user_id=7,
        requests=[request],
        watches=watches,
        prior_state=StateEntry(score=0),
        config=config,
        now=NOW,
    )

    assert result.reason == "penalized"
    assert result.score == 1


def test_movie_watch_is_matched_by_external_id():
    config = PolicyConfig(movie_grace_days=14)
    request = Request(
        request_id=3,
        user_id=7,
        media_type="movie",
        title="Some Localized Title",
        external_ids={"tmdb": "123"},
        created_at=days_ago(30),
    )
    watches = [
        Watch(
            user_id=7,
            media_type="movie",
            title="Different Title",
            external_ids={"tmdb": "123"},
            watched_at=days_ago(2),
            percent_complete=0.9,
        )
    ]

    result = evaluate_user(
        user_id=7,
        requests=[request],
        watches=watches,
        prior_state=StateEntry(score=1),
        config=config,
        now=NOW,
    )

    assert result.score == 0
    assert result.reason == "recovered"
