from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class Limits:
    movie_limit: int
    movie_days: int
    tv_limit: int
    tv_days: int


@dataclass(frozen=True)
class PolicyConfig:
    normal_limits: Limits = Limits(movie_limit=5, movie_days=3, tv_limit=1, tv_days=7)
    warning_limits: Limits = Limits(movie_limit=3, movie_days=7, tv_limit=1, tv_days=14)
    restricted_limits: Limits = Limits(movie_limit=1, movie_days=14, tv_limit=1, tv_days=30)
    warning_score: int = 1
    restricted_score: int = 3
    recovery_per_run: int = 1
    max_score: int = 10
    movie_grace_days: int = 14
    tv_grace_days: int = 21
    min_movie_fraction: float = 0.75
    min_tv_fraction: float = 0.2
    min_tv_episodes: int = 3
    lookback_days: int = 90


@dataclass(frozen=True)
class Request:
    request_id: int
    user_id: int
    media_type: str
    title: str
    created_at: datetime
    season_number: int | None = None
    episode_count: int | None = None
    external_ids: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Watch:
    user_id: int
    media_type: str
    title: str
    watched_at: datetime
    season_number: int | None = None
    episode_number: int | None = None
    percent_complete: float | None = None
    external_ids: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StateEntry:
    score: int = 0
    last_reason: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class Evaluation:
    user_id: int
    score: int
    prior_score: int
    reason: str
    limits: Limits
    matured_requests: int
    neglected_requests: int


def evaluate_user(
    *,
    user_id: int,
    requests: list[Request],
    watches: list[Watch],
    prior_state: StateEntry,
    config: PolicyConfig,
    now: datetime | None = None,
) -> Evaluation:
    now = now or datetime.now(UTC)
    relevant_requests = [
        request
        for request in requests
        if request.user_id == user_id and request.created_at >= now - timedelta(days=config.lookback_days)
    ]
    user_watches = [watch for watch in watches if watch.user_id == user_id]

    matured = [
        request
        for request in relevant_requests
        if now - request.created_at
        >= timedelta(days=config.movie_grace_days if request.media_type == "movie" else config.tv_grace_days)
    ]
    neglected = [request for request in matured if not _request_was_watched(request, user_watches, config)]

    prior_score = prior_state.score
    if neglected:
        reason = "penalized"
        score = min(config.max_score, prior_score + len(neglected))
    elif prior_score > 0:
        reason = "recovered"
        score = max(0, prior_score - config.recovery_per_run)
    else:
        reason = "unchanged"
        score = 0

    return Evaluation(
        user_id=user_id,
        score=score,
        prior_score=prior_score,
        reason=reason,
        limits=_limits_for_score(score, config),
        matured_requests=len(matured),
        neglected_requests=len(neglected),
    )


def _limits_for_score(score: int, config: PolicyConfig) -> Limits:
    if score >= config.restricted_score:
        return config.restricted_limits
    if score >= config.warning_score:
        return config.warning_limits
    return config.normal_limits


def _request_was_watched(request: Request, watches: list[Watch], config: PolicyConfig) -> bool:
    matches = [watch for watch in watches if _matches_request(request, watch)]
    if request.media_type == "movie":
        return any((watch.percent_complete or 1.0) >= config.min_movie_fraction for watch in matches)

    unique_episodes = {
        watch.episode_number for watch in matches if watch.media_type == "episode" and watch.episode_number is not None
    }
    watched_count = len(unique_episodes)
    episode_count = request.episode_count or max(config.min_tv_episodes, watched_count)
    required = max(config.min_tv_episodes, int(episode_count * config.min_tv_fraction))
    return watched_count >= required


def _matches_request(request: Request, watch: Watch) -> bool:
    if request.media_type == "movie" and watch.media_type != "movie":
        return False
    if request.media_type == "tv" and watch.media_type != "episode":
        return False
    if request.season_number is not None and watch.season_number != request.season_number:
        return False
    if _overlapping_external_id(request.external_ids, watch.external_ids):
        return True
    return _normalize_title(request.title) == _normalize_title(watch.title)


def _overlapping_external_id(left: dict[str, str], right: dict[str, str]) -> bool:
    for key, value in left.items():
        if value and right.get(key) == value:
            return True
    return False


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())
