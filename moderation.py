import discord
import datetime
from discord.ext import commands
import aiofiles
import asyncio

class Moderation(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        self.client.warnings[guild.id] = {}

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def warn(self, ctx, member: discord.Member = None, *, reason=None):
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")

        if reason is None:
            return await ctx.send("Please provide a reason for warning this user.")

        try:
            first_warning = False
            self.client.warnings[ctx.guild.id][member.id][0] += 1
            self.client.warnings[ctx.guild.id][member.id][1].append((ctx.author.id, reason))

        except KeyError:
            first_warning = True
            self.client.warnings[ctx.guild.id][member.id] = [1, [(ctx.author.id, reason)]]

        count = self.client.warnings[ctx.guild.id][member.id][0]

        async with aiofiles.open(f"{ctx.guild.id}.txt", mode="a") as file:
            await file.write(f"{member.id} {ctx.author.id} {reason}\n")

        await ctx.send(f"{member.mention} has {count} {'warning' if first_warning else 'warnings'}.")

        if count >= 3:
            await self.kick_after_warnings(ctx, member)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def warnings(self, ctx, member: discord.Member = None):
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")

        embed = discord.Embed(title=f"Displaying Warnings for {member.name}", description="", colour=discord.Colour.red())
        try:
            i = 1
            for admin_id, reason in self.client.warnings[ctx.guild.id][member.id][1]:
                admin = ctx.guild.get_member(admin_id)
                embed.description += f"**Warning {i}** given by: {admin.mention} for: *'{reason}'*.\n"
                i += 1

            await ctx.send(embed=embed)

        except KeyError:
            await ctx.send("This user has no warnings.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def kick(self, ctx, member: discord.Member = None, *, reason=None):
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

    async def kick_after_warnings(self, ctx, member: discord.Member):
        try:
            await member.send("You have been kicked from the server due to receiving 3 warnings.")
            await member.kick(reason="Exceeded 3 warnings")
            await ctx.send(f"{member.mention} has been kicked from the server due to receiving 3 warnings.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to kick members.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def ban(self, ctx, member: discord.Member = None, duration: int = None, *, reason=None):
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

def setup(client):
    client.add_cog(WarningsCog(client))
