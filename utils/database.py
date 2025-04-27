import motor.motor_asyncio
import redis.asyncio as redis
import os
import logging
import json
import datetime
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
    
    async def redis_lindex(self, name: str, index: int) -> Optional[str]:
        """Get an element from a list by its index"""
        value = await self.redis_client.lindex(name, index)
        return value.decode('utf-8') if value else None
    
    async def redis_llen(self, name: str) -> int:
        """Get the length of a list"""
        return await self.redis_client.llen(name)
    
    async def redis_ltrim(self, name: str, start: int, end: int):
        """Trim a list to the specified range"""
        return await self.redis_client.ltrim(name, start, end)
    
    async def redis_lset(self, name: str, index: int, value: str):
        """Set the value of an element in a list by its index"""
        return await self.redis_client.lset(name, index, value)
    
    # Music-specific methods
    
    # Queue management
    async def get_music_queue(self, guild_id: str) -> List[Dict]:
        """Get the music queue for a guild"""
        queue_key = f"music:queue:{guild_id}"
        queue_data = await self.redis_lrange(queue_key, 0, -1)
        return [json.loads(item) for item in queue_data]
    
    async def add_to_music_queue(self, guild_id: str, track_data: Dict):
        """Add a track to the end of a guild's music queue"""
        queue_key = f"music:queue:{guild_id}"
        serialized = json.dumps(track_data)
        return await self.redis_rpush(queue_key, serialized)
    
    async def clear_music_queue(self, guild_id: str):
        """Clear a guild's music queue"""
        queue_key = f"music:queue:{guild_id}"
        return await self.redis_delete(queue_key)
    
    async def remove_from_music_queue(self, guild_id: str, index: int) -> Optional[Dict]:
        """Remove a track from a guild's music queue by index"""
        queue_key = f"music:queue:{guild_id}"
        # Get the track first
        track_json = await self.redis_lindex(queue_key, index)
        if not track_json:
            return None
            
        # Create a temporary key
        temp_key = f"music:queue:{guild_id}:temp:{index}"
        await self.redis_set(temp_key, track_json, ex=60)  # Store temporarily with 60s expiration
        
        # Remove the track
        await self.redis_lset(queue_key, index, "TO_REMOVE")
        await self.redis_lrem(queue_key, 1, "TO_REMOVE")
        
        # Get the stored track and return it
        track_json = await self.redis_get(temp_key)
        await self.redis_delete(temp_key)
        
        return json.loads(track_json) if track_json else None
    
    # Currently playing track
    async def set_current_track(self, guild_id: str, track_data: Dict, ex: int = 3600):
        """Set the currently playing track for a guild with expiration"""
        current_key = f"music:current:{guild_id}"
        serialized = json.dumps(track_data)
        return await self.redis_set(current_key, serialized, ex=ex)
    
    async def get_current_track(self, guild_id: str) -> Optional[Dict]:
        """Get the currently playing track for a guild"""
        current_key = f"music:current:{guild_id}"
        track_json = await self.redis_get(current_key)
        return json.loads(track_json) if track_json else None
    
    async def clear_current_track(self, guild_id: str):
        """Clear the currently playing track for a guild"""
        current_key = f"music:current:{guild_id}"
        return await self.redis_delete(current_key)
    
    # Server settings
    async def get_music_settings(self, guild_id: str) -> Dict:
        """Get music settings for a guild"""
        settings = await self.find_one("music_settings", {"guild_id": guild_id})
        if not settings:
            # Default settings
            settings = {
                "guild_id": guild_id,
                "volume": 0.5,  # Default volume (0.0 to 1.0)
                "auto_play": False,  # Auto-play related tracks
                "repeat_mode": "off"  # off, single, queue
            }
            await self.insert_one("music_settings", settings)
        return settings
    
    async def update_music_settings(self, guild_id: str, settings: Dict):
        """Update music settings for a guild"""
        settings["guild_id"] = guild_id  # Ensure guild_id is set
        return await self.update_one(
            "music_settings", 
            {"guild_id": guild_id}, 
            {"$set": settings},
            upsert=True
        )
    
    # Playlists
    async def get_playlists(self, user_id: str) -> List[Dict]:
        """Get all playlists for a user"""
        return await self.find_many("music_playlists", {"user_id": user_id})
    
    async def get_playlist(self, playlist_id: str) -> Optional[Dict]:
        """Get a playlist by ID"""
        return await self.find_one("music_playlists", {"_id": playlist_id})
    
    async def create_playlist(self, user_id: str, name: str, tracks: List[Dict] = None) -> Dict:
        """Create a new playlist"""
        playlist = {
            "user_id": user_id,
            "name": name,
            "tracks": tracks or [],
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow()
        }
        result = await self.insert_one("music_playlists", playlist)
        playlist["_id"] = result.inserted_id
        return playlist
    
    async def update_playlist(self, playlist_id: str, update_data: Dict):
        """Update a playlist"""
        update_data["updated_at"] = datetime.datetime.utcnow()
        return await self.update_one(
            "music_playlists", 
            {"_id": playlist_id}, 
            {"$set": update_data}
        )
    
    async def delete_playlist(self, playlist_id: str):
        """Delete a playlist"""
        return await self.delete_one("music_playlists", {"_id": playlist_id})
    
    async def add_track_to_playlist(self, playlist_id: str, track_data: Dict):
        """Add a track to a playlist"""
        return await self.update_one(
            "music_playlists",
            {"_id": playlist_id},
            {
                "$push": {"tracks": track_data},
                "$set": {"updated_at": datetime.datetime.utcnow()}
            }
        )
    
    async def remove_track_from_playlist(self, playlist_id: str, track_index: int):
        """Remove a track from a playlist by index"""
        # First get the playlist to check if index is valid
        playlist = await self.get_playlist(playlist_id)
        if not playlist or track_index >= len(playlist.get("tracks", [])):
            return False
            
        # Remove the track at the specified index
        return await self.update_one(
            "music_playlists",
            {"_id": playlist_id},
            {
                "$unset": {f"tracks.{track_index}": 1},
                "$set": {"updated_at": datetime.datetime.utcnow()}
            }
        )
    
    # Statistics-related methods
    async def get_guild_stats(self, guild_id: str) -> Optional[Dict]:
        """Get statistics for a guild"""
        return await self.find_one("guild_stats", {"guild_id": guild_id})
    
    async def save_guild_stats(self, guild_id: str, stats: Dict):
        """Save statistics for a guild"""
        return await self.update_one(
            "guild_stats",
            {"guild_id": guild_id},
            {"$set": stats},
            upsert=True
        )
    
    async def delete_guild_stats(self, guild_id: str):
        """Delete statistics for a guild"""
        return await self.delete_one("guild_stats", {"guild_id": guild_id})
    
    async def get_stats_summary(self, guild_id: str) -> Dict:
        """Get a summary of statistics for a guild"""
        stats = await self.get_guild_stats(guild_id)
        if not stats:
            return {
                "member_count": 0,
                "message_count": 0,
                "command_count": 0,
                "voice_minutes": 0
            }
        
        return {
            "member_count": stats.get("member_count", {}).get("current", 0),
            "message_count": stats.get("messages", {}).get("total", 0),
            "command_count": stats.get("commands", {}).get("total", 0),
            "voice_minutes": stats.get("voice", {}).get("total_minutes", 0)
        }

# Create a singleton instance
db = Database()