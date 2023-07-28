import discord
import datetime
from discord.ext import commands
import aiofiles
import asyncio

class Moderation(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.muted_role_id = 0  # Replace with the ID of the muted role if you have one

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        self.client.warnings[guild.id] = {}

    # Existing code for warn, warnings, kick, and ban commands goes here

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def mute(self, ctx, member: discord.Member = None, duration: int = 0, *, reason=None):
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")

        if duration < 0:
            return await ctx.send("Please provide a valid mute duration in minutes (0 for permanent mute).")

        if reason is None:
            return await ctx.send("Please provide a reason for muting this user.")

        if self.muted_role_id == 0:
            return await ctx.send("Please set the muted role ID before using the mute command.")

        muted_role = ctx.guild.get_role(self.muted_role_id)
        if not muted_role:
            return await ctx.send("The muted role was not found on this server.")

        await member.add_roles(muted_role, reason=reason)

        if duration > 0:
            # Schedule the unmute task
            await asyncio.sleep(duration * 60)  # Sleep for the duration in seconds
            await member.remove_roles(muted_role, reason="Mute duration expired")

        await ctx.send(f"{member.mention} has been {'permanently ' if duration == 0 else f'muted for {duration} minutes '} for: {reason}")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def unmute(self, ctx, member: discord.Member = None):
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")

        if self.muted_role_id == 0:
            return await ctx.send("Please set the muted role ID before using the unmute command.")

        muted_role = ctx.guild.get_role(self.muted_role_id)
        if not muted_role:
            return await ctx.send("The muted role was not found on this server.")

        if muted_role not in member.roles:
            return await ctx.send(f"{member.mention} is not muted.")

        await member.remove_roles(muted_role, reason="Unmuted by moderator")
        await ctx.send(f"{member.mention} has been unmuted.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clear(self, ctx, limit: int):
        if limit <= 0:
            return await ctx.send("Please provide a valid number of messages to delete.")

        await ctx.channel.purge(limit=limit + 1)  # +1 to include the command message
        await ctx.send(f"{limit} messages have been deleted.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def tempban(self, ctx, member: discord.Member = None, duration: int = None, *, reason=None):
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