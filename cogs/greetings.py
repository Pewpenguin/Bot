import discord
from discord.ext import commands
import aiofiles

class Greeting(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.welcome_channels = {}
        self.goodbye_channels = {}

    def get_welcome_message(self, guild_id):
        if guild_id in self.welcome_channels:
            return self.welcome_channels[guild_id][1]
        return None

    def get_goodbye_message(self, guild_id):
        if guild_id in self.goodbye_channels:
            return self.goodbye_channels[guild_id][1]
        return None

    @commands.command()
    async def set_welcome_channel(self, ctx, new_channel: discord.TextChannel = None, *, message=None):
        if new_channel is not None and message is not None:
            for channel in ctx.guild.channels:
                if channel == new_channel:
                    self.welcome_channels[ctx.guild.id] = (channel.id, message)
                    await ctx.channel.send(f"Welcome channel has been set to: {channel.name} with the message {message}")
                    await channel.send("This is the new welcome channel!")

                    async with aiofiles.open("welcome_channels.txt", mode="a") as file:
                        await file.write(f"{ctx.guild.id} {new_channel.id} {message}\n")

                    return
            await ctx.channel.send("No matching text channel found in the specified category.")
        else:
            await ctx.channel.send("You didn't include the name of a welcome channel or a welcome message.")

    @commands.command()
    async def set_goodbye_channel(self, ctx, new_channel: discord.TextChannel = None, *, message=None):
        if new_channel is not None and message is not None:
            for channel in ctx.guild.channels:
                if channel == new_channel:
                    self.goodbye_channels[ctx.guild.id] = (channel.id, message)
                    await ctx.channel.send(f"Goodbye channel has been set to: {channel.name} with the message {message}")
                    await channel.send("This is the new goodbye channel!")

                    async with aiofiles.open("goodbye_channels.txt", mode="a") as file:
                        await file.write(f"{ctx.guild.id} {new_channel.id} {message}\n")

                    return

            await ctx.channel.send("Couldn't find the given channel.")

        else:
            await ctx.channel.send("You didn't include the name of a goodbye channel or a goodbye message.")

    @commands.command()
    async def preview_welcome(self, ctx):
        message = self.get_welcome_message(ctx.guild.id)
        if message is not None:
            await ctx.send(f"Preview of welcome message:\n{message}")
        else:
            await ctx.send("Welcome message has not been set for this server.")

    @commands.command()
    async def preview_goodbye(self, ctx):
        message = self.get_goodbye_message(ctx.guild.id)
        if message is not None:
            await ctx.send(f"Preview of goodbye message:\n{message}")
        else:
            await ctx.send("Goodbye message has not been set for this server.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        message = self.get_welcome_message(member.guild.id)
        if message is not None:
            channel_id = self.welcome_channels[member.guild.id][0]
            channel = member.guild.get_channel(channel_id)
            await channel.send(f"{message} {member.mention}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        message = self.get_goodbye_message(member.guild.id)
        if message is not None:
            channel_id = self.goodbye_channels[member.guild.id][0]
            channel = member.guild.get_channel(channel_id)
            await channel.send(f"{message} {member.mention}")