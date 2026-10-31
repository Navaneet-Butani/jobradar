"""Redis connection and management."""

import logging
from typing import Optional
import redis.asyncio as redis
from app.config.settings import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis connection manager."""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self._connection_url = settings.redis_url
    
    async def connect(self) -> None:
        """Initialize Redis connection."""
        try:
            if not self._connection_url:
                logger.info("REDIS_URL not set; running without Redis (caching and rate limits degrade gracefully)")
                return
            logger.info("Connecting to Redis...")
            
            # Try multiple connection methods
            connection_methods = [
                # Method 1: Using URL
                lambda: redis.from_url(
                    self._connection_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=20,
                    retry_on_timeout=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    health_check_interval=30,
                ),
                # Method 2: Using direct connection
                lambda: redis.Redis(
                    host="localhost",
                    port=6379,
                    db=0,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    max_connections=20,
                    health_check_interval=30,
                ),
                # Method 3: Using 127.0.0.1 instead of localhost
                lambda: redis.Redis(
                    host="127.0.0.1",
                    port=6379,
                    db=0,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    max_connections=20,
                    health_check_interval=30,
                ),
            ]
            
            for i, method in enumerate(connection_methods, 1):
                try:
                    logger.info(f"Trying connection method {i}...")
                    self.client = method()
                    
                    # Test the connection
                    pong = await self.client.ping()
                    logger.info(f"Redis connection successful with method {i}: {pong}")
                    return
                    
                except Exception as method_error:
                    logger.warning(f"Connection method {i} failed: {method_error}")
                    if self.client:
                        try:
                            await self.client.close()
                        except:
                            pass
                        self.client = None
                    continue
            
            # If all methods failed
            logger.error("All Redis connection methods failed")
            self.client = None
                
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Don't raise exception for Redis failure - it's optional
            self.client = None
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client:
            logger.info("Closing Redis connection...")
            await self.client.close()
            self.client = None
            logger.info("Redis connection closed")
    
    async def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            if not self.client:
                return False
            
            result = await self.client.ping()
            return result is True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        if not self.client:
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET failed for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set value in Redis."""
        if not self.client:
            return False
        try:
            await self.client.set(key, value, ex=ex)
            return True
        except Exception as e:
            logger.error(f"Redis SET failed for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        if not self.client:
            return False
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE failed for key {key}: {e}")
            return False

    async def ping(self) -> bool:
        """Ping Redis server."""
        if not self.client:
            return False
        try:
            result = await self.client.ping()
            return result is True
        except Exception as e:
            logger.error(f"Redis PING failed: {e}")
            return False

    async def lpush(self, key: str, value: str) -> bool:
        """Push value to the left of a list."""
        if not self.client:
            return False
        try:
            await self.client.lpush(key, value)
            return True
        except Exception as e:
            logger.error(f"Redis LPUSH failed for key {key}: {e}")
            return False


# Global Redis manager instance
redis_manager = RedisManager()


def get_redis_client() -> Optional[redis.Redis]:
    """Return the shared Redis client, or None if not connected yet."""
    return redis_manager.client


# Alias — some callers import get_redis() instead of get_redis_client()
get_redis = get_redis_client
