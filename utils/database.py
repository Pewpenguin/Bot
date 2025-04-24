import motor.motor_asyncio
import redis.asyncio as redis
import os
import logging
from typing import Dict, List, Tuple, Any, Optional, Union

logger = logging.getLogger('bot.database')

class Database:
    """Database connection manager for MongoDB and Redis"""
    
    def __init__(self):
        self.mongo_client = None
        self.mongo_db = None
        self.redis_client = None
        self.connected = False
    
    async def connect(self, mongo_uri: str, redis_uri: str, db_name: str = "discord_bot"):
        """Connect to MongoDB and Redis"""
        try:
            # Connect to MongoDB
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
            self.mongo_db = self.mongo_client[db_name]
            
            # Connect to Redis
            self.redis_client = await redis.from_url(redis_uri)
            
            # Test connections
            await self.mongo_db.command('ping')
            await self.redis_client.ping()
            
            self.connected = True
            logger.info("Successfully connected to MongoDB and Redis")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to databases: {str(e)}")
            return False
    
    async def close(self):
        """Close database connections"""
        if self.mongo_client:
            self.mongo_client.close()
        if self.redis_client:
            await self.redis_client.close()
        self.connected = False
        logger.info("Database connections closed")
    
    # MongoDB operations
    async def find_one(self, collection: str, query: Dict):
        """Find a single document in MongoDB"""
        return await self.mongo_db[collection].find_one(query)
    
    async def find_many(self, collection: str, query: Dict):
        """Find multiple documents in MongoDB"""
        cursor = self.mongo_db[collection].find(query)
        return await cursor.to_list(length=None)
    
    async def insert_one(self, collection: str, document: Dict):
        """Insert a single document into MongoDB"""
        return await self.mongo_db[collection].insert_one(document)
    
    async def insert_many(self, collection: str, documents: List[Dict]):
        """Insert multiple documents into MongoDB"""
        return await self.mongo_db[collection].insert_many(documents)
    
    async def update_one(self, collection: str, query: Dict, update: Dict, upsert: bool = False):
        """Update a single document in MongoDB"""
        return await self.mongo_db[collection].update_one(query, update, upsert=upsert)
    
    async def update_many(self, collection: str, query: Dict, update: Dict):
        """Update multiple documents in MongoDB"""
        return await self.mongo_db[collection].update_many(query, update)
    
    async def delete_one(self, collection: str, query: Dict):
        """Delete a single document from MongoDB"""
        return await self.mongo_db[collection].delete_one(query)
    
    async def delete_many(self, collection: str, query: Dict):
        """Delete multiple documents from MongoDB"""
        return await self.mongo_db[collection].delete_many(query)
    
    # Redis operations
    async def redis_set(self, key: str, value: str, ex: Optional[int] = None):
        """Set a key-value pair in Redis with optional expiration"""
        return await self.redis_client.set(key, value, ex=ex)
    
    async def redis_get(self, key: str) -> Optional[str]:
        """Get a value from Redis by key"""
        value = await self.redis_client.get(key)
        return value.decode('utf-8') if value else None
    
    async def redis_delete(self, key: str):
        """Delete a key from Redis"""
        return await self.redis_client.delete(key)
    
    async def redis_exists(self, key: str) -> bool:
        """Check if a key exists in Redis"""
        return await self.redis_client.exists(key) > 0
    
    async def redis_expire(self, key: str, seconds: int):
        """Set expiration time for a key"""
        return await self.redis_client.expire(key, seconds)
    
    async def redis_hset(self, name: str, key: str, value: str):
        """Set a hash field to a value in Redis"""
        return await self.redis_client.hset(name, key, value)
    
    async def redis_hget(self, name: str, key: str) -> Optional[str]:
        """Get the value of a hash field in Redis"""
        value = await self.redis_client.hget(name, key)
        return value.decode('utf-8') if value else None
    
    async def redis_hgetall(self, name: str) -> Dict[str, str]:
        """Get all fields and values in a hash in Redis"""
        result = await self.redis_client.hgetall(name)
        return {k.decode('utf-8'): v.decode('utf-8') for k, v in result.items()} if result else {}
    
    async def redis_hdel(self, name: str, key: str):
        """Delete a hash field in Redis"""
        return await self.redis_client.hdel(name, key)
    
    async def redis_lpush(self, name: str, *values):
        """Push values onto the head of a list in Redis"""
        return await self.redis_client.lpush(name, *values)
    
    async def redis_rpush(self, name: str, *values):
        """Push values onto the tail of a list in Redis"""
        return await self.redis_client.rpush(name, *values)
    
    async def redis_lrange(self, name: str, start: int, end: int) -> List[str]:
        """Get a range of elements from a list in Redis"""
        result = await self.redis_client.lrange(name, start, end)
        return [item.decode('utf-8') for item in result] if result else []
    
    async def redis_lrem(self, name: str, count: int, value: str):
        """Remove elements from a list in Redis"""
        return await self.redis_client.lrem(name, count, value)

# Create a singleton instance
db = Database()