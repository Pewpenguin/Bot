import discord
from discord.ext import commands
import datetime
import aiofiles
import asyncio
import aiohttp
import logging
import os

from config.config import BOT_TOKEN
from config.logging_config import setup_logging
from utils.ffmpeg_check import check_ffmpeg, get_ffmpeg_path
from cogs.role import Role
from cogs.greetings import Greeting
from cogs.moderation import Moderation
from cogs.polls import Polls
from cogs.music import Music
from cogs.help import Help

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
    
    client.reaction_roles = []
    client.welcome_channels = {}
    client.goodbye_channels = {}
    client.warnings = {}

    for guild in client.guilds:
        client.warnings[guild.id] = {}

    # Initialize data files in the data directory
    data_files = ["data/reaction_roles.txt", "data/welcome_channels.txt", "data/goodbye_channels.txt"]
    for file in data_files:
        async with aiofiles.open(file, mode="a") as temp:
            pass

    async with aiofiles.open("data/reaction_roles.txt", mode="r") as file:
        lines = await file.readlines()
        for line in lines:
            data = line.split(" ")
            client.reaction_roles.append((int(data[0]), int(data[1]), data[2].strip("\n")))

    async with aiofiles.open("data/welcome_channels.txt", mode="r") as file:
        lines = await file.readlines()
        for line in lines:
            data = line.split(" ")
            client.welcome_channels[int(data[0])] = (int(data[1]), " ".join(data[2:]).strip("\n"))

    async with aiofiles.open("data/goodbye_channels.txt", mode="r") as file:
        lines = await file.readlines()
        for line in lines:
            data = line.split(" ")
            client.goodbye_channels[int(data[0])] = (int(data[1]), " ".join(data[2:]).strip("\n"))

    for guild in client.guilds:
        async with aiofiles.open(f"{guild.id}.txt", mode="a") as temp:
            pass

        async with aiofiles.open(f"{guild.id}.txt", mode="r") as file:
            lines = await file.readlines()

            for line in lines:
                data = line.split(" ")
                member_id = int(data[0])
                admin_id = int(data[1])
                reason = " ".join(data[2:]).strip("\n")

                try:
                    client.warnings[guild.id][member_id][0] += 1
                    client.warnings[guild.id][member_id][1].append((admin_id, reason))
                except KeyError:
                    client.warnings[guild.id][member_id] = [1, [(admin_id, reason)]]

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
async def run_bot():
    await client.start(BOT_TOKEN)
    

async def main():
    await asyncio.gather(run_bot(), setup())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        asyncio.run(client.close())
