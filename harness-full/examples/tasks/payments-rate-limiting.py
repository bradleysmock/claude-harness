# Example: payments-rate-limiting.py
# Place in .harness/tasks/
#
# Dependency graph:
#
#   redis-rate-limiter ──┐
#                        ├──► payments-rate-limit-middleware ──► payments-middleware-registration
#   rate-limit-config  ──┘

from harness import Spec
from harness.task_models import Task, TaskSpec

task = Task(
    id="payments-rate-limiting",
    description="Add per-user sliding-window rate limiting to the payments API using Redis.",
    specs=[

        TaskSpec(
            spec=Spec(
                id="redis-rate-limiter",
                description=(
                    "A RedisRateLimiter class that enforces a sliding window rate limit "
                    "using Redis sorted sets. Generic — not payments-specific."
                ),
                constraints=[
                    "Uses redis.asyncio.Redis — not the sync client",
                    "Sliding window via sorted sets: ZADD + ZREMRANGEBYSCORE + ZCARD",
                    "Constructor: __init__(self, redis: Redis, key_prefix: str, "
                    "limit: int, window_seconds: int)",
                    "is_allowed(user_id: str) -> bool — catches all Redis errors, "
                    "logs a warning, returns True (fail open policy)",
                    "remaining(user_id: str) -> int — calls remaining in window",
                    "reset_at(user_id: str) -> datetime — UTC time window resets",
                ],
                acceptance_criteria=[
                    "11th call within window returns False from is_allowed()",
                    "remaining() returns 0 after limit is reached",
                    "Redis connection error causes is_allowed() to return True, not raise",
                    "Separate key_prefix values are fully isolated from each other",
                    "reset_at() returns a future datetime while within an active window",
                ],
                metadata={
                    "target_file": "src/core/redis_rate_limiter.py",
                    "reference_files": [],
                },
            ),
            depends_on=[],
        ),

        TaskSpec(
            spec=Spec(
                id="rate-limit-config",
                description=(
                    "A RateLimitSettings class that loads rate limit parameters "
                    "from environment variables using pydantic-settings."
                ),
                constraints=[
                    "Extends AppSettings from core/config.py — do not create a new base",
                    "PAYMENTS_RATE_LIMIT_MAX: int = 10",
                    "PAYMENTS_RATE_LIMIT_WINDOW_SECONDS: int = 60",
                    "Follow the exact pydantic-settings pattern used in core/config.py",
                ],
                acceptance_criteria=[
                    "Defaults apply when environment variables are absent",
                    "Environment variables override defaults when present",
                    "Non-integer values raise ValidationError on startup, not at call time",
                ],
                metadata={
                    "target_file": "src/core/rate_limit_config.py",
                    "reference_files": ["src/core/config.py"],
                },
            ),
            depends_on=[],   # independent of redis-rate-limiter
        ),

        TaskSpec(
            spec=Spec(
                id="payments-rate-limit-middleware",
                description=(
                    "FastAPI middleware that enforces per-user rate limiting on the "
                    "payments router using RedisRateLimiter and RateLimitSettings. "
                    "Note: RedisRateLimiter and RateLimitSettings APIs will be injected "
                    "automatically by the harness from upstream spec outputs."
                ),
                constraints=[
                    # RedisRateLimiter and RateLimitSettings injected automatically
                    "Extracts user_id from JWT via get_current_user() in auth/dependencies.py",
                    "Returns 429 with Retry-After header (seconds until reset_at()) on limit exceeded",
                    "Apply only to routes under /api/payments — not globally",
                    "Follow the middleware pattern in api/middleware/request_id.py",
                ],
                acceptance_criteria=[
                    "Returns 429 on the 11th request within the rate limit window",
                    "Retry-After header is present and contains an integer seconds value",
                    "GET /api/payments is unaffected (read-only routes exempt)",
                    "Redis failure results in the request proceeding — never a 500",
                ],
                metadata={
                    "target_file": "src/api/middleware/payments_rate_limit.py",
                    "reference_files": [
                        "src/api/middleware/request_id.py",
                        "src/auth/dependencies.py",
                    ],
                },
            ),
            depends_on=["redis-rate-limiter", "rate-limit-config"],
        ),

        TaskSpec(
            spec=Spec(
                id="payments-middleware-registration",
                description=(
                    "Register the payments rate limit middleware on the payments router "
                    "in the existing application factory. "
                    "Note: middleware API will be injected automatically by the harness."
                ),
                constraints=[
                    # Middleware API injected automatically from upstream spec
                    "Modify only src/api/routers/payments.py",
                    "Do not touch src/main.py, other routers, or middleware files",
                    "Middleware must wrap the router as its outermost layer",
                ],
                acceptance_criteria=[
                    "All pre-existing payments router tests continue to pass",
                    "POST /api/payments triggers rate limit enforcement",
                    "GET /api/payments does not trigger rate limit enforcement",
                ],
                metadata={
                    "target_file": "src/api/routers/payments.py",
                    "reference_files": ["src/api/routers/payments.py"],
                },
            ),
            depends_on=["payments-rate-limit-middleware"],
        ),

    ],
)
