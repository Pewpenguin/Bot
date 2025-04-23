import discord
import datetime
from discord.ext import commands
import aiofiles
import asyncio

class Moderation(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.muted_role_id = 0  

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        self.client.warnings[guild.id] = {}

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def mute(self, ctx, member: discord.Member = None, duration: int = 0, *, reason=None):
        """Mute a member in the server.
        
        Applies the muted role to a member, preventing them from sending messages.
        You can specify a duration in minutes or mute permanently (duration = 0).
        
        Usage:
        !mute @member [duration] [reason]
        
        Parameters:
        - member: The member to mute (mention or ID)
        - duration: Time in minutes (0 for permanent mute)
        - reason: Reason for the mute
        
        Example:
        !mute @User 30 Spamming in chat
        !mute @User 0 Repeated rule violations
        """
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
        """Unmute a previously muted member.
        
        Removes the muted role from a member, allowing them to send messages again.
        
        Usage:
        !unmute @member
        
        Parameters:
        - member: The member to unmute (mention or ID)
        
        Example:
        !unmute @User
        """
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
        """Clear a specified number of messages from the channel.
        
        Bulk deletes recent messages from the current channel.
        Discord limits this to messages newer than 14 days old.
        
        Usage:
        !clear [number]
        
        Parameters:
        - number: The number of messages to delete (1-100)
        
        Example:
        !clear 50
        """
        if limit <= 0:
            return await ctx.send("Please provide a valid number of messages to delete.")

        await ctx.channel.purge(limit=limit + 1)  
        await ctx.send(f"{limit} messages have been deleted.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def tempban(self, ctx, member: discord.Member = None, duration: int = None, *, reason=None):
        """Temporarily ban a member from the server.
        
        Bans a member for a specified duration in minutes, then automatically unbans them.
        The member will receive a DM with the ban reason if possible.
        
        Usage:
        !tempban @member [duration] [reason]
        
        Parameters:
        - member: The member to ban (mention or ID)
        - duration: Time in minutes before automatic unban
        - reason: Reason for the ban
        
        Example:
        !tempban @User 1440 Repeated rule violations (24 hour ban)
        """
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")

        if duration is None or duration <= 0:
            return await ctx.send("Please provide a valid ban duration in minutes.")

        if reason is None:
            return await ctx.send("Please provide a reason for banning this user.")

        try:
            await member.send(f"You have been banned from {ctx.guild.name} for {duration} minutes. Reason: {reason}")
            await ctx.guild.ban(member, reason=reason)  

            unban_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=duration)

            await asyncio.sleep(duration * 60)  
            await ctx.guild.unban(member, reason="Ban duration expired")

            await ctx.send(f"{member.mention} has been banned from the server for {duration} minutes. Reason: {reason}")

        except discord.Forbidden:
            return await ctx.send("I don't have the necessary permissions to ban members.")