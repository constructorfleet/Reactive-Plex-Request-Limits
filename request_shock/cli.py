from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Any

from request_shock.clients import OverseerrClient, TautulliClient
from request_shock.config import load_config
from request_shock.policy import Limits, PolicyConfig, StateEntry, evaluate_user
from request_shock.state import load_state, save_state, updated_entry


def is_exempt_user(user: Any, raw_config: dict[str, Any]) -> bool:
    exemptions = _user_match_config(raw_config.get("exempt_users", {}) or {})
    ignored_ids = _normalized_id_set(raw_config.get("ignore_user_ids", [])) | exemptions["ids"]
    if int(user.id) in ignored_ids:
        return True

    return _user_matches(user, exemptions)


def should_apply_policy_to_user(user: Any, raw_config: dict[str, Any]) -> bool:
    apply_users = _user_match_config(raw_config.get("apply_users", {}) or {})
    if not any(apply_users.values()):
        return True
    return int(user.id) in apply_users["ids"] or _user_matches(user, apply_users)


def _user_matches(user: Any, matches: dict[str, set[Any]]) -> bool:
    return (
        _normalize(getattr(user, "username", None)) in matches["usernames"]
        or _normalize(getattr(user, "plex_username", None)) in matches["plex_usernames"]
        or _normalize(getattr(user, "email", None)) in matches["emails"]
    )


def should_notify_throttle(*, prior_score: int, new_score: int, config: PolicyConfig) -> bool:
    return _tier(prior_score, config) < _tier(new_score, config)


def build_throttle_message(
    *,
    username: str,
    score: int,
    limits: Limits,
    notification_config: dict[str, Any],
) -> tuple[str, str]:
    values = {
        "username": username,
        "score": score,
        "movie_limit": limits.movie_limit,
        "movie_days": limits.movie_days,
        "tv_limit": limits.tv_limit,
        "tv_days": limits.tv_days,
    }
    subject_template = notification_config.get("subject", "Overseerr request limits updated")
    body_template = notification_config.get(
        "body",
        "Ah ah ah, {username}. Your request limits have been throttled: "
        "{movie_limit} movies per {movie_days} days and {tv_limit} TV season per {tv_days} days.",
    )
    return subject_template.format(**values), body_template.format(**values)


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt Overseerr request limits from Tautulli watch history.")
    parser.add_argument("--config", type=Path, default=Path("config.yml"))
    parser.add_argument("--state", type=Path, default=Path("request-shock-state.json"))
    parser.add_argument("--dry-run", action="store_true", help="Evaluate and print changes without updating Overseerr.")
    args = parser.parse_args()

    raw_config, policy = load_config(args.config)
    overseerr_config = raw_config["overseerr"]
    tautulli_config = raw_config["tautulli"]
    notification_config = raw_config.get("notifications", {}) or {}
    notifier_ids = [int(notifier_id) for notifier_id in notification_config.get("tautulli_notifier_ids", [])]

    overseerr = OverseerrClient(overseerr_config["url"], overseerr_config["api_key"])
    tautulli = TautulliClient(
        tautulli_config["url"],
        tautulli_config["api_key"],
        verify_ssl=tautulli_config.get("verify_ssl", True),
    )
    state = load_state(args.state)

    try:
        for user in overseerr.list_users():
            user_id = int(user.id)
            username = _display_name(user)
            if is_exempt_user(user, raw_config):
                print(f"skip user={username}: exempt")
                continue

            if not should_apply_policy_to_user(user, raw_config):
                print(f"skip user={username}: not in apply_users")
                continue

            if not username:
                print(f"skip user {user_id}: no username available for Tautulli lookup")
                continue

            requests = overseerr.list_requests(user_id)
            watches = tautulli.history_for_user(username=username, length=tautulli_config.get("history_length", 1000))
            prior = state.get(str(user_id), StateEntry())
            result = evaluate_user(
                user_id=user_id,
                requests=requests,
                watches=[replace(watch, user_id=user_id) for watch in watches],
                prior_state=prior,
                config=policy,
            )
            settings = overseerr.get_user_settings(user_id)
            current = (
                settings.get("movieQuotaLimit"),
                settings.get("movieQuotaDays"),
                settings.get("tvQuotaLimit"),
                settings.get("tvQuotaDays"),
            )
            target = (
                result.limits.movie_limit,
                result.limits.movie_days,
                result.limits.tv_limit,
                result.limits.tv_days,
            )
            print(
                f"user={username} score={result.prior_score}->{result.score} "
                f"reason={result.reason} neglected={result.neglected_requests}/{result.matured_requests} "
                f"limits={target}"
            )
            if current != target and not args.dry_run:
                overseerr.set_limits(user_id, result.limits, settings)
            if notifier_ids and should_notify_throttle(
                prior_score=result.prior_score, new_score=result.score, config=policy
            ):
                subject, body = build_throttle_message(
                    username=username,
                    score=result.score,
                    limits=result.limits,
                    notification_config=notification_config,
                )
                if args.dry_run:
                    print(f"dry run: would notify user={username} subject={subject!r}")
                else:
                    for notifier_id in notifier_ids:
                        tautulli.notify(notifier_id=notifier_id, subject=subject, body=body)
            state[str(user_id)] = updated_entry(result.score, result.reason)

        if not args.dry_run:
            save_state(args.state, state)
    finally:
        overseerr.close()

    if args.dry_run:
        print("dry run: no Overseerr settings or state file were changed")
    return 0


def _display_name(user: Any) -> str | None:
    return getattr(user, "plex_username", None) or getattr(user, "username", None) or getattr(user, "email", None)


def _tier(score: int, config: PolicyConfig) -> int:
    if score >= config.restricted_score:
        return 2
    if score >= config.warning_score:
        return 1
    return 0


def _normalized_set(values: list[Any]) -> set[str]:
    return {_normalize(value) for value in values}


def _user_match_config(config: dict[str, Any]) -> dict[str, set[Any]]:
    return {
        "ids": _normalized_id_set(config.get("ids", [])),
        "usernames": _normalized_set(config.get("usernames", [])),
        "plex_usernames": _normalized_set(config.get("plex_usernames", [])),
        "emails": _normalized_set(config.get("emails", [])),
    }


def _normalized_id_set(values: list[Any]) -> set[int]:
    return {int(value) for value in values}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


if __name__ == "__main__":
    raise SystemExit(main())
