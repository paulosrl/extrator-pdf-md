import json
import redis as redis_sync

from app.config import settings

_redis_client = None


def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_sync.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def publish_progress(job_id: str, payload: dict) -> None:
    channel = f"progress:{job_id}"
    get_redis().publish(channel, json.dumps(payload))


def subscribe_progress(job_id: str):
    r = redis_sync.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    pubsub.subscribe(f"progress:{job_id}")
    return pubsub
