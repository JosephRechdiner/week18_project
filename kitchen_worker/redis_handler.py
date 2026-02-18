from redis import Redis
import os

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
REDIS_DB = int(os.getenv("REDIS_DB"))

# ========================================================================
# REDIS
# ========================================================================

class RedisManager:
    r = None
    def __init__(self):
        try:
            if not RedisManager.r:
                RedisManager.r = Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    db=REDIS_DB,
                    decode_responses=True)
            self.r = RedisManager.r
            
        except Exception as e:
            raise Exception(f"Could not init redis, Error: {str(e)}")
