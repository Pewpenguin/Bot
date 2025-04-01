import discord
from discord.ext import commands
import datetime
import aiofiles
import asyncio
import aiohttp

from config.config import BOT_TOKEN
from cogs.role import Role
from cogs.greetings import Greeting
from cogs.moderation import Moderation
from cogs.polls import Polls

intents = discord.Intents.all()
client = commands.Bot(command_prefix='!', intents=intents, help_command=None)


@client.event
async def on_ready():
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
            
async def get_help_embed():
    em = discord.Embed(title="Help!", description="", color=discord.Color.green())
    em.description += f"**{client.command_prefix}set_reaction <role> <msg> <emoji>** : Sets the reaction role for the given role, message, and emoji.\n"
    em.description += f"**{client.command_prefix}set_welcome_channel <new-channel> <welcome-message>** : Sets the guild's welcome channel to the given channel and the welcome message to the given message.\n"
    avatar_url = client.user.avatar.url if client.user.avatar else None
    em.set_footer(text="Thanks for using me!", icon_url=avatar_url)
    return em


@client.event
async def on_message(message):
    if client.user.mentioned_in(message):
        em = await get_help_embed()
        await message.channel.send(embed=em)

    await client.process_commands(message)


@client.command()
async def help(ctx):
    em = await get_help_embed()
    await ctx.send(embed=em)
         
async def setup():
    await client.wait_until_ready()
    await client.add_cog(Role(client))
    await client.add_cog(Greeting(client))
    await client.add_cog(Moderation(client))
    await client.add_cog(Polls(client))
async def run_bot():
    await client.start(BOT_TOKEN)
    

async def main():
    await asyncio.gather(run_bot(), setup())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        asyncio.run(client.close())
