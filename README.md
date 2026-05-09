# request-shock

Adaptive Overseerr request limits based on whether users actually watch what they request.

The script uses the `overseerr` Python client for Overseerr and the `tautulli` Python client for Tautulli. Overseerr is the place where per-user request quotas are changed. Tautulli is the evidence source for watch history and, optionally, the delivery mechanism for throttle notifications.

## How It Works

Each run does this:

1. Loads users and their request history from Overseerr.
2. Skips exempt users.
3. Pulls each user's movie/episode watch history from Tautulli.
4. Ignores requests that are still inside the grace period.
5. Marks mature requests as watched or neglected.
6. Increases the user's local shock score for neglected mature requests.
7. Decreases the shock score by `recovery_per_run` when there are no neglected mature requests.
8. Writes the target request limits back to Overseerr unless running with `--dry-run`.
9. Optionally triggers configured Tautulli notification agents when the user moves into a stricter tier.

The score is stored in `request-shock-state.json`. Overseerr does not know about the score; it only sees the resulting quota override.

## Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp config.example.yml config.yml
```

Edit `config.yml` with your Overseerr and Tautulli URLs/API keys.

## Running

Dry run:

```sh
.venv/bin/python -m request_shock --config config.yml --state request-shock-state.json --dry-run
```

Apply changes:

```sh
.venv/bin/python -m request_shock --config config.yml --state request-shock-state.json
```

Run it daily from cron, systemd timer, Unraid User Scripts, or whatever scheduler owns your media automation.

Docker:

```sh
docker run --rm \
  -v "$PWD/config.yml:/config.yml:ro" \
  -v "$PWD/request-shock-state.json:/request-shock-state.json" \
  ghcr.io/OWNER/REPO:latest \
  --config /config.yml \
  --state /request-shock-state.json
```

Replace `OWNER/REPO` with the GitHub repository path after the release workflow publishes the image.

Docker Compose:

```sh
cp .env.example .env
docker compose build
docker compose run --rm request-shock --config /config.yml --state /request-shock-state.json --dry-run
docker compose run --rm request-shock
```

The Compose file mounts `config.yml` read-only and stores the local score state in `request-shock-state.json`.

## Development

This repo includes a devcontainer at `.devcontainer/devcontainer.json`. It uses the `dev` Dockerfile target and installs the package with development dependencies.

Local checks:

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
.venv/bin/python -m build
docker build -t request-shock:local .
```

## Releases

PRs run lint, format, build, tests, and a Docker image build.

When a PR is merged into `main`, the release workflow reads the merged PR labels and bumps `pyproject.toml`:

- `patch`: `0.1.0` to `0.1.1`
- `minor`: `0.1.0` to `0.2.0`
- `major`: `0.1.0` to `1.0.0`
- `breaking`: same as `major`

If multiple release labels are present, the highest-impact label wins. If no release label is present, the release workflow fails before publishing so the missing version intent is visible.

After bumping the version, the workflow tags the commit and publishes the Docker image to:

```text
ghcr.io/OWNER/REPO:latest
ghcr.io/OWNER/REPO:<version>
ghcr.io/OWNER/REPO:<short-sha>
```

## Exempt Users

Use `exempt_users` for users the policy should never touch. Matching is case-insensitive.

```yaml
exempt_users:
  ids:
    - 1
  usernames:
    - local_admin
  plex_usernames:
    - GoodFriend
  emails:
    - partner@example.com
```

The older `ignore_user_ids` setting still works and is treated the same as `exempt_users.ids`.

## Apply Users

Use `apply_users` when you want to test the policy on a small set of users before rolling it out. Matching works the same way as `exempt_users` and is case-insensitive.

```yaml
apply_users:
  ids:
    - 7
  usernames:
    - local_test_user
  plex_usernames:
    - PlexTestUser
  emails:
    - tester@example.com
```

When `apply_users` is missing, or all four lists are empty, the policy applies to every non-exempt user. When any `apply_users` list has entries, only matching users are evaluated; everyone else is skipped before requests, watch history, settings, or notifications are processed.

## Notifications

To notify users when they get throttled, configure one or more Tautulli notifier IDs:

```yaml
notifications:
  tautulli_notifier_ids:
    - 3
  subject: "Overseerr request limits updated"
  body: "Ah ah ah, {username}. Your request limits have been throttled: {movie_limit} movies per {movie_days} days and {tv_limit} TV season per {tv_days} days."
```

The script calls Tautulli's `notify` API for each configured notifier ID. Delivery stays in Tautulli, so the notifier can be Discord, email, Pushover, a webhook, or whatever agent you already configured there.

Notifications are sent only when the score crosses into a stricter tier:

- Full quota to warning quota: notify.
- Warning score increases but remains warning quota: do not notify again.
- Warning quota to restricted quota: notify.
- Restricted quota remains restricted: do not notify again.
- Recovery to a less strict tier: do not send the throttle message.

Available message placeholders:

- `{username}`
- `{score}`
- `{movie_limit}`
- `{movie_days}`
- `{tv_limit}`
- `{tv_days}`

## Quota Tiers

Default tiers:

```yaml
normal_limits:
  movie_limit: 5
  movie_days: 3
  tv_limit: 1
  tv_days: 7
warning_limits:
  movie_limit: 3
  movie_days: 7
  tv_limit: 1
  tv_days: 14
restricted_limits:
  movie_limit: 1
  movie_days: 14
  tv_limit: 1
  tv_days: 30
```

`warning_score` controls when a user leaves full quota. `restricted_score` controls when they hit the strictest quota. With the defaults, score `0` is full quota, scores `1-2` are warning quota, and score `3+` is restricted quota.

## Watch Thresholds

Movies count as watched when Tautulli indicates at least `min_movie_fraction` complete. Default: `0.75`.

TV seasons count as watched when the user watches at least:

```text
max(min_tv_episodes, floor(episode_count * min_tv_fraction))
```

With the default `min_tv_fraction: 0.2` and `min_tv_episodes: 3`:

- 8-episode season requires 3 watched episodes.
- 10-episode season requires 3 watched episodes.
- 24-episode season requires 4 watched episodes.
- 70-episode season requires 14 watched episodes.

`min_tv_episodes` is a floor for short seasons. It is not a loophole for giant seasons.

## Recovery Examples

Assume the script runs once per day, `recovery_per_run: 1`, `warning_score: 1`, and `restricted_score: 3`.

### Example 1: One Bad Movie Request

Taylor requests a movie and does not watch it within `movie_grace_days`.

- Day 1: request is new, no penalty.
- Day 15: request is mature and unwatched. Score goes `0 -> 1`; warning limits apply.
- Day 16: Taylor watches at least 75% of the movie. No neglected mature requests remain. Score goes `1 -> 0`; full quota returns.

### Example 2: Big Season, Token Watching

Taylor requests a 70-episode season and watches one episode.

- Day 1: request is new, no penalty.
- Day 22: request is mature. Required watched episodes are `14`; watched episodes are `1`. Score goes `0 -> 1`; warning limits apply.
- Day 23: still only one episode watched. The same request is still neglected, so score can climb again depending on the current lookback window.
- Once Taylor watches 14 distinct episodes, that request stops counting as neglected. The score then recovers by `recovery_per_run` each run.

### Example 3: Restricted User Watches Their Backlog

Taylor has score `3`, so restricted limits apply.

- Taylor watches enough of the mature neglected requests.
- Next run: no neglected mature requests remain, score `3 -> 2`; warning limits apply.
- Following run: still clean, score `2 -> 1`; warning limits still apply.
- Following run: still clean, score `1 -> 0`; full quota returns.

This is intentionally gradual. One cleanup day does not instantly erase a sustained pattern.

### Example 4: Recovery By Waiting

Taylor ignores old requests but stops making new ones.

- Neglected requests continue to count while they are inside `lookback_days`.
- After they age out of `lookback_days`, they no longer affect evaluation.
- From that point, if there are no remaining neglected mature requests, the score decays by `recovery_per_run` each run until full quota returns.

Waiting works, but it is slower than watching what was requested because recovery does not start until the neglected requests fall out of the lookback window.

## Dry Runs

Dry runs print target limits and notification actions without updating Overseerr, notifying through Tautulli, or writing the state file.

Use dry runs after config changes:

```sh
.venv/bin/python -m request_shock --config config.yml --state request-shock-state.json --dry-run
```
