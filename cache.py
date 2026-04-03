"""
Redis cache helper for the AI chatbot.

Provides:
- Redis connection with graceful fallback (no Redis → in-memory dict)
- Response caching keyed by a hash of the conversation context (TTL: 24 h)
- Conversation-history persistence in Redis (TTL: 7 days)
- Cache hit/miss statistics stored as Redis counters
"""

import hashlib
import json
import os
import time
import redis

# ── TTL constants ──────────────────────────────────────────────────────────────
RESPONSE_TTL     = 24 * 60 * 60        # 24 hours  – for cached Gemini responses
HISTORY_TTL      = 7  * 24 * 60 * 60   # 7 days    – for conversation history
MAX_HISTORY_TURNS = 40                  # Maximum conversation turns to persist

# ── Key prefixes ──────────────────────────────────────────────────────────────
_KEY_RESPONSE    = "chat_response:"
_KEY_HISTORY     = "chat_history:"
_KEY_STAT_HITS   = "cache_stats:hits"
_KEY_STAT_MISSES = "cache_stats:misses"

# How many seconds to wait before retrying a failed connection
_RECONNECT_INTERVAL = 60


def _connect() -> "redis.Redis | None":
    """
    Return an authenticated Redis client, or None if the server is unreachable.
    Connection settings are taken from environment variables:
      REDIS_HOST     (default: localhost)
      REDIS_PORT     (default: 6379)
      REDIS_DB       (default: 0)
      REDIS_PASSWORD (optional)
    """
    host     = os.environ.get("REDIS_HOST", "localhost")
    port     = int(os.environ.get("REDIS_PORT", 6379))
    db       = int(os.environ.get("REDIS_DB", 0))
    password = os.environ.get("REDIS_PASSWORD") or None

    try:
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        client.ping()
        return client
    except (redis.ConnectionError, redis.TimeoutError, OSError):
        return None


# Module-level state
_client: "redis.Redis | None" = _connect()
_last_attempt: float = time.monotonic()

# In-process fallback stores used when Redis is unavailable
_mem_responses: "dict[str, str]"  = {}
_mem_histories: "dict[str, list]" = {}
_mem_stats: "dict[str, int]"      = {"hits": 0, "misses": 0}


def is_available() -> bool:
    """
    Return True if the Redis connection is alive.

    Avoids hammering a downed Redis server: after a failed ping, a new
    connection attempt is only made after *_RECONNECT_INTERVAL* seconds.
    """
    global _client, _last_attempt

    if _client is not None:
        try:
            _client.ping()
            return True
        except (redis.ConnectionError, redis.TimeoutError, OSError):
            _client = None
            _last_attempt = time.monotonic()
            return False

    # Don't retry too frequently
    if time.monotonic() - _last_attempt < _RECONNECT_INTERVAL:
        return False

    _last_attempt = time.monotonic()
    _client = _connect()
    return _client is not None


# ── Response cache ─────────────────────────────────────────────────────────────

def _response_key(session_id: str, user_message: str, history: list) -> str:
    """Deterministic cache key derived from the full conversation context."""
    payload = json.dumps(
        {"session": session_id, "message": user_message, "history": history},
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{_KEY_RESPONSE}{digest}"


def get_cached_response(session_id: str, user_message: str, history: list) -> str | None:
    """
    Look up a previously cached Gemini response.
    Returns the full reply string on a cache hit, None on a miss.
    """
    key = _response_key(session_id, user_message, history)

    if is_available():
        try:
            value = _client.get(key)
            if value is not None:
                _client.incr(_KEY_STAT_HITS)
                return value
            _client.incr(_KEY_STAT_MISSES)
            return None
        except redis.RedisError:
            pass

    # Fallback
    if key in _mem_responses:
        _mem_stats["hits"] += 1
        return _mem_responses[key]
    _mem_stats["misses"] += 1
    return None


def set_cached_response(
    session_id: str, user_message: str, history: list, response: str
) -> None:
    """Persist a Gemini response in the cache with a 24-hour TTL."""
    key = _response_key(session_id, user_message, history)

    if is_available():
        try:
            _client.setex(key, RESPONSE_TTL, response)
            return
        except redis.RedisError:
            pass

    _mem_responses[key] = response


# ── Conversation history ───────────────────────────────────────────────────────

def get_history(session_id: str) -> list:
    """Retrieve the conversation history list for *session_id*."""
    key = f"{_KEY_HISTORY}{session_id}"

    if is_available():
        try:
            raw = _client.get(key)
            if raw:
                return json.loads(raw)
            return []
        except (redis.RedisError, json.JSONDecodeError):
            pass

    return _mem_histories.get(session_id, [])


def set_history(session_id: str, history: list) -> None:
    """Persist the conversation history with a 7-day TTL (keep last MAX_HISTORY_TURNS turns)."""
    trimmed = history[-MAX_HISTORY_TURNS:]
    key     = f"{_KEY_HISTORY}{session_id}"

    if is_available():
        try:
            _client.setex(key, HISTORY_TTL, json.dumps(trimmed))
            return
        except redis.RedisError:
            pass

    _mem_histories[session_id] = trimmed


def clear_history(session_id: str) -> None:
    """Delete the conversation history for *session_id*."""
    key = f"{_KEY_HISTORY}{session_id}"

    if is_available():
        try:
            _client.delete(key)
            return
        except redis.RedisError:
            pass

    _mem_histories.pop(session_id, None)


# ── Statistics ────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """Return a dict with cache hit/miss counts and Redis availability."""
    if is_available():
        try:
            hits   = int(_client.get(_KEY_STAT_HITS)   or 0)
            misses = int(_client.get(_KEY_STAT_MISSES) or 0)
            total  = hits + misses
            return {
                "redis_available": True,
                "hits":   hits,
                "misses": misses,
                "total":  total,
                "hit_rate": round(hits / total * 100, 1) if total else 0.0,
            }
        except redis.RedisError:
            pass

    hits   = _mem_stats["hits"]
    misses = _mem_stats["misses"]
    total  = hits + misses
    return {
        "redis_available": False,
        "hits":   hits,
        "misses": misses,
        "total":  total,
        "hit_rate": round(hits / total * 100, 1) if total else 0.0,
    }
