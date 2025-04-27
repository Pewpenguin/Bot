import discord
from discord.ext import commands
import datetime
import asyncio
import aiohttp
import logging
import os

from config.config import BOT_TOKEN, MONGO_URI, REDIS_URI
from config.logging_config import setup_logging
from utils.ffmpeg_check import check_ffmpeg, get_ffmpeg_path
from utils.database import db
from cogs.role import Role
from cogs.greetings import Greeting
from cogs.moderation import Moderation
from cogs.polls import Polls
from cogs.music import Music
from cogs.help import Help
from cogs.statistics import Statistics

intents = discord.Intents.all()
client = commands.Bot(command_prefix='!', intents=intents)


@client.event
async def on_ready():
    # Setup logging
    root_logger, music_logger = setup_logging()
    root_logger.info("Bot is starting up")
    music_logger.info("Music system initializing")
    
    # Check FFmpeg installation
    is_ffmpeg_installed, ffmpeg_info = check_ffmpeg()
    if is_ffmpeg_installed:
        music_logger.info(f"FFmpeg is properly installed: {ffmpeg_info}")
        ffmpeg_path = get_ffmpeg_path()
        if ffmpeg_path:
            music_logger.info(f"FFmpeg path: {ffmpeg_path}")
    else:
        music_logger.error(f"FFmpeg is not properly installed: {ffmpeg_info}")
        music_logger.error("Music functionality may not work without FFmpeg!")
        print("\033[91mWARNING: FFmpeg is not properly installed. Music functionality may not work!\033[0m")
    
    # Initialize database connections
    db_logger = logging.getLogger('bot.database')
    db_connected = await db.connect(MONGO_URI, REDIS_URI)
    if db_connected:
        db_logger.info("Successfully connected to MongoDB and Redis")
    else:
        db_logger.error("Failed to connect to databases. Bot may not function correctly!")
        print("\033[91mWARNING: Database connection failed. Bot may not function correctly!\033[0m")
    
    # Initialize data structures
    client.warnings = {}
    for guild in client.guilds:
        client.warnings[guild.id] = {}
        
        # Load warnings from MongoDB
        warnings_data = await db.find_many("warnings", {"guild_id": guild.id})
        for warning in warnings_data:
            member_id = warning["member_id"]
            admin_id = warning["admin_id"]
            reason = warning["reason"]
            
            try:
                if member_id not in client.warnings[guild.id]:
                    client.warnings[guild.id][member_id] = [0, []]
                client.warnings[guild.id][member_id][0] += 1
                client.warnings[guild.id][member_id][1].append((admin_id, reason))
            except Exception as e:
                db_logger.error(f"Error loading warning: {str(e)}")
    
    print("The client is online")
    print("------------------")    
            
@client.event
async def on_message(message):
    await client.process_commands(message)
         
async def setup():
    await client.wait_until_ready()
    await client.add_cog(Role(client))
    await client.add_cog(Greeting(client))
    await client.add_cog(Moderation(client))
    await client.add_cog(Polls(client))
    await client.add_cog(Music(client))
    await client.add_cog(Help(client))
    await client.add_cog(Statistics(client))
async def run_bot():
    await client.start(BOT_TOKEN)
    

async def main():
    await asyncio.gather(run_bot(), setup())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Close database connections before exiting
        asyncio.run(db.close())
        asyncio.run(client.close())
