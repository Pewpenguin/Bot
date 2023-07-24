import discord
from discord.ext import commands
import datetime
import aiofiles
import asyncio
import aiohttp

from config import BOT_TOKEN

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

    for file in ["reaction_roles.txt", "welcome_channels.txt", "goodbye_channels.txt"]:
        async with aiofiles.open(file, mode="a") as temp:
            pass

    async with aiofiles.open("reaction_roles.txt", mode="r") as file:
        lines = await file.readlines()
        for line in lines:
            data = line.split(" ")
            client.reaction_roles.append((int(data[0]), int(data[1]), data[2].strip("\n")))

    async with aiofiles.open("welcome_channels.txt", mode="r") as file:
        lines = await file.readlines()
        for line in lines:
            data = line.split(" ")
            client.welcome_channels[int(data[0])] = (int(data[1]), " ".join(data[2:]).strip("\n"))

    async with aiofiles.open("goodbye_channels.txt", mode="r") as file:
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
async def on_raw_reaction_add(payload):
    for role_id, msg_id, emoji in client.reaction_roles:
        if msg_id == payload.message_id and emoji == str(payload.emoji.name.encode("utf-8")):
            guild = client.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            await member.add_roles(guild.get_role(role_id))
            return


@client.event
async def on_raw_reaction_remove(payload):
    for role_id, msg_id, emoji in client.reaction_roles:
        if msg_id == payload.message_id and emoji == str(payload.emoji.name.encode("utf-8")):
            guild = client.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            await member.remove_roles(guild.get_role(role_id))
            return

@client.command()
async def set_reaction(ctx, role: discord.Role = None, msg: discord.Message = None, emoji=None):
    if role is not None and msg is not None and emoji is not None:
        await msg.add_reaction(emoji)
        client.reaction_roles.append((role.id, msg.id, str(emoji.encode("utf-8"))))

        async with aiofiles.open("reaction_roles.txt", mode="a") as file:
            emoji_utf = emoji.encode("utf-8")
            await file.write(f"{role.id} {msg.id} {emoji_utf}\n")

        await ctx.send("Reaction has been set.")
    else:
        await ctx.send("Invalid arguments.")
        
@client.command()
async def set_welcome_channel(ctx, new_channel: discord.TextChannel = None, *, message=None):
    if new_channel is not None and message is not None:
        for channel in ctx.guild.channels:
            if channel == new_channel:
                client.welcome_channels[ctx.guild.id] = (channel.id, message)
                await ctx.channel.send(f"Welcome channel has been set to: {channel.name} with the message {message}")
                await channel.send("This is the new welcome channel!")

                async with aiofiles.open("welcome_channels.txt", mode="a") as file:
                    await file.write(f"{ctx.guild.id} {new_channel.id} {message}\n")

                return
        await ctx.channel.send("No matching text channel found in the specified category.")
    else:
        await ctx.channel.send("You didn't include the name of a welcome channel or a welcome message.")


@client.command()
async def set_goodbye_channel(ctx, new_channel: discord.TextChannel = None, *, message=None):
    if new_channel is not None and message is not None:
        for channel in ctx.guild.channels:
            if channel == new_channel:
                client.goodbye_channels[ctx.guild.id] = (channel.id, message)
                await ctx.channel.send(f"Goodbye channel has been set to: {channel.name} with the message {message}")
                await channel.send("This is the new goodbye channel!")

                async with aiofiles.open("goodbye_channels.txt", mode="a") as file:
                    await file.write(f"{ctx.guild.id} {new_channel.id} {message}\n")

                return

        await ctx.channel.send("Couldn't find the given channel.")

    else:
        await ctx.channel.send("You didn't include the name of a goodbye channel or a goodbye message.")
        
@client.event
async def on_member_join(member):
    for guild_id in client.welcome_channels:
        if guild_id == member.guild.id:
            channel_id, message = client.welcome_channels[guild_id]
            channel = member.guild.get_channel(channel_id)
            await channel.send(f"{message} {member.mention}")
            return
        

@client.event
async def on_member_remove(member):
    for guild_id in client.goodbye_channels:
        if guild_id == member.guild.id:
            channel_id, message = client.goodbye_channels[guild_id]
            channel = member.guild.get_channel(channel_id)
            await channel.send(f"{message} {member.mention}")
            return

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


@client.event
async def on_guild_join(guild):
    client.warnings[guild.id] = {}


@client.command()
@commands.has_permissions(administrator=True)
async def warn(ctx, member: discord.Member = None, *, reason=None):
    if member is None:
        return await ctx.send("The provided member could not be found or you forgot to provide one.")

    if reason is None:
        return await ctx.send("Please provide a reason for warning this user.")

    try:
        first_warning = False
        client.warnings[ctx.guild.id][member.id][0] += 1
        client.warnings[ctx.guild.id][member.id][1].append((ctx.author.id, reason))

    except KeyError:
        first_warning = True
        client.warnings[ctx.guild.id][member.id] = [1, [(ctx.author.id, reason)]]

    count = client.warnings[ctx.guild.id][member.id][0]

    async with aiofiles.open(f"{ctx.guild.id}.txt", mode="a") as file:
        await file.write(f"{member.id} {ctx.author.id} {reason}\n")

    await ctx.send(f"{member.mention} has {count} {'warning' if first_warning else 'warnings'}.")


@client.command()
@commands.has_permissions(administrator=True)
async def warnings(ctx, member: discord.Member = None):
    if member is None:
        return await ctx.send("The provided member could not be found or you forgot to provide one.")

    embed = discord.Embed(title=f"Displaying Warnings for {member.name}", description="", colour=discord.Colour.red())
    try:
        i = 1
        for admin_id, reason in client.warnings[ctx.guild.id][member.id][1]:
            admin = ctx.guild.get_member(admin_id)
            embed.description += f"**Warning {i}** given by: {admin.mention} for: *'{reason}'*.\n"
            i += 1

        await ctx.send(embed=embed)

    except KeyError:
        await ctx.send("This user has no warnings.")


@client.command()
@commands.has_permissions(administrator=True)
async def kick(ctx, member: discord.Member = None, *, reason=None):
    if member is None:
        return await ctx.send("The provided member could not be found or you forgot to provide one.")

    if reason is None:
        return await ctx.send("Please provide a reason for kicking this user.")

    try:
        await member.send(f"You have been kicked from {ctx.guild.name}. Reason: {reason}")
        await member.kick(reason=reason)  # Kick the member from the server
        await ctx.send(f"{member.mention} has been kicked from the server. Reason: {reason}")
    except discord.Forbidden:
        return await ctx.send("I don't have the necessary permissions to kick members.")

@client.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, member: discord.Member = None, duration: int = None, *, reason=None):
    if member is None:
        return await ctx.send("The provided member could not be found or you forgot to provide one.")

    if duration is None or duration <= 0:
        return await ctx.send("Please provide a valid ban duration in minutes.")

    if reason is None:
        return await ctx.send("Please provide a reason for banning this user.")

    try:
        await member.send(f"You have been banned from {ctx.guild.name} for {duration} minutes. Reason: {reason}")
        await ctx.guild.ban(member, reason=reason)  # Ban the member from the server

        # Calculate the unban time
        unban_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=duration)

        # Schedule the unban task
        await asyncio.sleep(duration * 60)  # Sleep for the duration in seconds
        await ctx.guild.unban(member, reason="Ban duration expired")

        await ctx.send(f"{member.mention} has been banned from the server for {duration} minutes. Reason: {reason}")

    except discord.Forbidden:
        return await ctx.send("I don't have the necessary permissions to ban members.")
         
async def setup():
    await client.wait_until_ready()
async def run_bot():
    await client.start(BOT_TOKEN)
    

async def main():
    await asyncio.gather(run_bot(), setup())
     
loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(main())
except KeyboardInterrupt:
    loop.run_until_complete(client.close())
finally:
    loop.close()
