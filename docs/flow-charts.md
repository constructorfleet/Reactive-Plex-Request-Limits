# Flow Charts and Runtime Notes

This document turns the policy into a set of quick reference diagrams so it is easier to understand what the job does on each run, how a user's score changes, and which external systems are involved.

## End-to-End Run Flow

```mermaid
flowchart TD
    A[Start CLI run] --> B[Load config.yml]
    B --> C[Load request-shock-state.json]
    C --> D[Create Seerr/Overseerr client]
    D --> E[Create Tautulli client]
    E --> F[List users from Seerr or Overseerr]
    F --> G{Next user}
    G -->|Exempt| H[Skip user]
    G -->|Not in apply_users| I[Skip user]
    G -->|No usable username| J[Skip user]
    G -->|Evaluate| K[List user requests]
    K --> L[Load Tautulli watch history]
    L --> M[Evaluate score and target limits]
    M --> N[Read current request-limit settings]
    N --> O{Dry run?}
    O -->|Yes| P[Print proposed changes only]
    O -->|No| Q{Limits changed?}
    Q -->|Yes| R[Write new limits to Seerr or Overseerr]
    Q -->|No| S[Keep current limits]
    P --> T{Moved to stricter tier?}
    R --> T
    S --> T
    T -->|Yes + dry run| U[Print notification preview]
    T -->|Yes + live run| V[Send Tautulli notifications]
    T -->|No| W[Skip notification]
    U --> X[Update in-memory score state]
    V --> X
    W --> X
    H --> Y{More users?}
    I --> Y
    J --> Y
    X --> Y
    Y -->|Yes| G
    Y -->|No + dry run| Z[Exit without saving state]
    Y -->|No + live run| AA[Save request-shock-state.json and exit]
```

## Score Evaluation Flow

```mermaid
flowchart TD
    A[Requests in lookback window] --> B[Filter to current user]
    B --> C[Split into mature vs still in grace period]
    C --> D[Match mature requests against watch history]
    D --> E{Any mature neglected requests?}
    E -->|Yes| F[Increase score by neglected count]
    E -->|No| G{Prior score above zero?}
    G -->|Yes| H[Decrease score by recovery_per_run]
    G -->|No| I[Keep score at zero]
    F --> J[Clamp to max_score]
    H --> K[Clamp to zero floor]
    I --> L[Choose limits by score tier]
    J --> L
    K --> L
    L --> M{Score >= restricted_score?}
    M -->|Yes| N[Restricted limits]
    M -->|No| O{Score >= warning_score?}
    O -->|Yes| P[Warning limits]
    O -->|No| Q[Normal limits]
```

### Matching Rules Used During Evaluation

- Only requests inside `lookback_days` are considered.
- A movie becomes mature after `movie_grace_days`.
- A TV season becomes mature after `tv_grace_days`.
- Movie requests count as watched when playback reaches at least `min_movie_fraction`.
- TV requests count as watched when the user has watched at least `max(min_tv_episodes, floor(episode_count * min_tv_fraction))` distinct episodes for the requested season.
- Request/watch matching prefers overlapping external IDs (`tmdb`, `tvdb`, `imdb`) and falls back to normalized title matching.

## Integration and Data Flow

```mermaid
flowchart LR
    A[config.yml] --> B[CLI runtime]
    C[request-shock-state.json] --> B
    B --> D[Seerr or Overseerr API]
    B --> E[Tautulli API]
    D --> F[Users]
    D --> G[User requests]
    D --> H[Current quota settings]
    E --> I[Watch history]
    B --> J[Policy evaluation]
    J --> K[Target quota limits]
    K --> D
    J --> L[Updated local score state]
    L --> C
    J --> M{Entered stricter tier?}
    M -->|Yes| E
```

## Configuration-to-Behavior Map

| Config area | What it controls |
| --- | --- |
| `seerr` / `overseerr` | Which request-manager API is updated with the final quota override |
| `tautulli` | Where watch history comes from and where optional notifications are sent |
| `ignore_user_ids` / `exempt_users` | Users the policy never touches |
| `apply_users` | Optional allow-list for staged rollouts |
| `policy.normal_limits` | Quota values when score is below `warning_score` |
| `policy.warning_limits` | Quota values when score is at or above `warning_score` but below `restricted_score` |
| `policy.restricted_limits` | Quota values when score is at or above `restricted_score` |
| `policy.movie_grace_days` / `policy.tv_grace_days` | How long a request can age before it can count against a user |
| `policy.min_movie_fraction`, `policy.min_tv_fraction`, `policy.min_tv_episodes` | What "watched enough" means for movies and TV seasons |
| `policy.lookback_days` | How far back the evaluator looks for request history |
| `policy.recovery_per_run` / `policy.max_score` | Score decay and upper bound |
| `notifications` | Whether stricter-tier transitions trigger Tautulli notifier calls |

## Related Docs

- See [`../README.md`](../README.md) for setup, operations, and examples.
- See [`user-request-limit-update.md`](user-request-limit-update.md) for the end-user explanation of why limits may change.
