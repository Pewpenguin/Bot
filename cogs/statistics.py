import discord
import asyncio
import logging
import datetime
import json
from discord.ext import commands, tasks
from typing import Dict, List, Optional, Union
from utils.database import db

logger = logging.getLogger('bot.statistics')

class Statistics(commands.Cog):
    """Track and display server statistics"""
    
    def __init__(self, bot):
        self.bot = bot
        self.stats_cache = {}
        self.update_interval = 5 * 60  # 5 minutes in seconds
        
        # Start background tasks
        self.aggregate_stats_task.start()
        self.save_stats_task.start()
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.aggregate_stats_task.cancel()
        self.save_stats_task.cancel()
    
    async def initialize_guild_stats(self, guild_id: str):
        """Initialize statistics tracking for a guild"""
        if guild_id not in self.stats_cache:
            # Try to load from database first
            stats = await db.get_guild_stats(guild_id)
            
            if not stats:
                # Create new stats object if none exists
                stats = {
                    "guild_id": guild_id,
                    "member_count": {
                        "current": 0,
                        "history": []
                    },
                    "messages": {
                        "total": 0,
                        "by_channel": {},
                        "by_hour": {str(i): 0 for i in range(24)},
                        "by_day": {str(i): 0 for i in range(7)}
                    },
                    "commands": {
                        "total": 0,
                        "by_name": {}
                    },
                    "voice": {
                        "total_minutes": 0,
                        "by_channel": {}
                    },
                    "last_updated": datetime.datetime.utcnow().isoformat()
                }
                
                # Save initial stats
                await db.save_guild_stats(guild_id, stats)
            
            # Store in cache
            self.stats_cache[guild_id] = stats
    
    @tasks.loop(minutes=5.0)
    async def aggregate_stats_task(self):
        """Periodically aggregate statistics"""
        try:
            logger.info("Running stats aggregation task")
            for guild in self.bot.guilds:
                guild_id = str(guild.id)
                
                # Initialize stats for this guild if needed
                await self.initialize_guild_stats(guild_id)
                
                # Update member count history
                current_count = guild.member_count
                timestamp = datetime.datetime.utcnow().isoformat()
                
                # Update member count
                self.stats_cache[guild_id]["member_count"]["current"] = current_count
                
                # Add to history (keep last 30 days of hourly data)
                history = self.stats_cache[guild_id]["member_count"]["history"]
                history.append({"count": current_count, "timestamp": timestamp})
                
                # Limit history size (24 * 30 = 720 entries for hourly data over 30 days)
                if len(history) > 720:
                    self.stats_cache[guild_id]["member_count"]["history"] = history[-720:]
                
                # Update last_updated timestamp
                self.stats_cache[guild_id]["last_updated"] = timestamp
                
                logger.debug(f"Updated stats for guild {guild_id}")
        except Exception as e:
            logger.error(f"Error in stats aggregation task: {str(e)}", exc_info=True)
    
    @aggregate_stats_task.before_loop
    async def before_aggregate_stats(self):
        """Wait for bot to be ready before starting task"""
        await self.bot.wait_until_ready()
    
    @tasks.loop(minutes=15.0)
    async def save_stats_task(self):
        """Periodically save statistics to database"""
        try:
            logger.info("Running stats save task")
            for guild_id, stats in self.stats_cache.items():
                await db.save_guild_stats(guild_id, stats)
                logger.debug(f"Saved stats for guild {guild_id} to database")
        except Exception as e:
            logger.error(f"Error in stats save task: {str(e)}", exc_info=True)
    
    @save_stats_task.before_loop
    async def before_save_stats(self):
        """Wait for bot to be ready before starting task"""
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Track message statistics"""
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Ignore DMs
        if not message.guild:
            return
            
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        
        # Initialize stats for this guild if needed
        await self.initialize_guild_stats(guild_id)
        
        # Update total message count
        self.stats_cache[guild_id]["messages"]["total"] += 1
        
        # Update by-channel stats
        channel_stats = self.stats_cache[guild_id]["messages"]["by_channel"]
        if channel_id not in channel_stats:
            channel_stats[channel_id] = 0
        channel_stats[channel_id] += 1
        
        # Update by-hour stats
        hour = str(datetime.datetime.utcnow().hour)
        self.stats_cache[guild_id]["messages"]["by_hour"][hour] += 1
        
        # Update by-day stats
        day = str(datetime.datetime.utcnow().weekday())
        self.stats_cache[guild_id]["messages"]["by_day"][day] += 1
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Track command usage statistics"""
        # Ignore DMs
        if not ctx.guild:
            return
            
        guild_id = str(ctx.guild.id)
        command_name = ctx.command.qualified_name
        
        # Initialize stats for this guild if needed
        await self.initialize_guild_stats(guild_id)
        
        # Update total command count
        self.stats_cache[guild_id]["commands"]["total"] += 1
        
        # Update by-name stats
        command_stats = self.stats_cache[guild_id]["commands"]["by_name"]
        if command_name not in command_stats:
            command_stats[command_name] = 0
        command_stats[command_name] += 1
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Track voice channel usage statistics"""
        # Ignore bots
        if member.bot:
            return
            
        guild_id = str(member.guild.id)
        
        # Initialize stats for this guild if needed
        await self.initialize_guild_stats(guild_id)
        
        # If user joined a voice channel
        if before.channel is None and after.channel is not None:
            # Store join time in Redis with 24h expiration
            channel_id = str(after.channel.id)
            join_time = datetime.datetime.utcnow().isoformat()
            await db.redis_set(f"voice_join:{guild_id}:{member.id}", 
                              f"{channel_id}:{join_time}", 
                              ex=86400)  # 24 hours
        
        # If user left a voice channel
        elif before.channel is not None and (after.channel is None or after.channel.id != before.channel.id):
            # Get join time from Redis
            join_data = await db.redis_get(f"voice_join:{guild_id}:{member.id}")
            if join_data:
                channel_id, join_time_str = join_data.split(':', 1)
                join_time = datetime.datetime.fromisoformat(join_time_str)
                leave_time = datetime.datetime.utcnow()
                
                # Calculate duration in minutes
                duration_minutes = (leave_time - join_time).total_seconds() / 60
                
                # Update voice stats
                self.stats_cache[guild_id]["voice"]["total_minutes"] += duration_minutes
                
                # Update by-channel stats
                channel_stats = self.stats_cache[guild_id]["voice"]["by_channel"]
                if channel_id not in channel_stats:
                    channel_stats[channel_id] = 0
                channel_stats[channel_id] += duration_minutes
                
                # Remove join time from Redis
                await db.redis_delete(f"voice_join:{guild_id}:{member.id}")
    
    @commands.group(name="stats", invoke_without_command=True)
    async def stats(self, ctx):
        """Display server statistics"""
        if ctx.invoked_subcommand is None:
            guild_id = str(ctx.guild.id)
            
            # Initialize stats for this guild if needed
            await self.initialize_guild_stats(guild_id)
            
            # Get stats from cache
            stats = self.stats_cache[guild_id]
            
            # Create embed
            embed = discord.Embed(
                title=f"📊 Statistics for {ctx.guild.name}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            
            # Add member count
            embed.add_field(
                name="👥 Members",
                value=f"Current: {stats['member_count']['current']}",
                inline=True
            )
            
            # Add message stats
            embed.add_field(
                name="💬 Messages",
                value=f"Total: {stats['messages']['total']}",
                inline=True
            )
            
            # Add command stats
            embed.add_field(
                name="⌨️ Commands",
                value=f"Total: {stats['commands']['total']}",
                inline=True
            )
            
            # Add voice stats
            embed.add_field(
                name="🎤 Voice",
                value=f"Total: {int(stats['voice']['total_minutes'])} minutes",
                inline=True
            )
            
            # Add last updated timestamp
            last_updated = datetime.datetime.fromisoformat(stats["last_updated"])
            embed.set_footer(text=f"Last updated: {last_updated.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            await ctx.send(embed=embed)
    
    @stats.command(name="messages")
    async def stats_messages(self, ctx):
        """Display detailed message statistics"""
        guild_id = str(ctx.guild.id)
        
        # Initialize stats for this guild if needed
        await self.initialize_guild_stats(guild_id)
        
        # Get stats from cache
        stats = self.stats_cache[guild_id]
        message_stats = stats["messages"]
        
        # Create embed
        embed = discord.Embed(
            title=f"💬 Message Statistics for {ctx.guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add total messages
        embed.add_field(
            name="Total Messages",
            value=str(message_stats["total"]),
            inline=False
        )
        
        # Add top 5 channels
        channel_stats = message_stats["by_channel"]
        if channel_stats:
            # Sort channels by message count
            sorted_channels = sorted(channel_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            
            channels_text = ""
            for channel_id, count in sorted_channels:
                channel = ctx.guild.get_channel(int(channel_id))
                channel_name = channel.name if channel else f"Unknown ({channel_id})"
                channels_text += f"#{channel_name}: {count} messages\n"
            
            embed.add_field(
                name="Top Channels",
                value=channels_text or "No data",
                inline=False
            )
        
        # Add by-hour stats
        hour_stats = message_stats["by_hour"]
        if hour_stats:
            hours_text = ""
            peak_hour = max(hour_stats.items(), key=lambda x: x[1])[0]
            peak_count = hour_stats[peak_hour]
            
            hours_text += f"Peak hour: {peak_hour}:00 UTC ({peak_count} messages)\n"
            
            embed.add_field(
                name="Time Statistics",
                value=hours_text or "No data",
                inline=False
            )
        
        # Add by-day stats
        day_stats = message_stats["by_day"]
        if day_stats:
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            peak_day_idx = max(day_stats.items(), key=lambda x: x[1])[0]
            peak_day = days[int(peak_day_idx)]
            peak_day_count = day_stats[peak_day_idx]
            
            days_text = f"Most active day: {peak_day} ({peak_day_count} messages)\n"
            
            embed.add_field(
                name="Day Statistics",
                value=days_text or "No data",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @stats.command(name="commands")
    async def stats_commands(self, ctx):
        """Display detailed command usage statistics"""
        guild_id = str(ctx.guild.id)
        
        # Initialize stats for this guild if needed
        await self.initialize_guild_stats(guild_id)
        
        # Get stats from cache
        stats = self.stats_cache[guild_id]
        command_stats = stats["commands"]
        
        # Create embed
        embed = discord.Embed(
            title=f"⌨️ Command Usage Statistics for {ctx.guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add total commands
        embed.add_field(
            name="Total Commands Used",
            value=str(command_stats["total"]),
            inline=False
        )
        
        # Add top 10 commands
        by_name = command_stats["by_name"]
        if by_name:
            # Sort commands by usage count
            sorted_commands = sorted(by_name.items(), key=lambda x: x[1], reverse=True)[:10]
            
            commands_text = ""
            for cmd_name, count in sorted_commands:
                commands_text += f"{cmd_name}: {count} uses\n"
            
            embed.add_field(
                name="Top Commands",
                value=commands_text or "No data",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @stats.command(name="members")
    async def stats_members(self, ctx):
        """Display member count statistics"""
        guild_id = str(ctx.guild.id)
        
        # Initialize stats for this guild if needed
        await self.initialize_guild_stats(guild_id)
        
        # Get stats from cache
        stats = self.stats_cache[guild_id]
        member_stats = stats["member_count"]
        
        # Create embed
        embed = discord.Embed(
            title=f"👥 Member Statistics for {ctx.guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add current count
        embed.add_field(
            name="Current Member Count",
            value=str(member_stats["current"]),
            inline=False
        )
        
        # Add history info if available
        history = member_stats["history"]
        if len(history) > 1:
            oldest = history[0]
            newest = history[-1]
            
            oldest_count = oldest["count"]
            oldest_time = datetime.datetime.fromisoformat(oldest["timestamp"])
            
            change = newest["count"] - oldest_count
            change_sign = "+" if change >= 0 else ""
            
            time_diff = datetime.datetime.utcnow() - oldest_time
            days = time_diff.days
            
            embed.add_field(
                name=f"Change over {days} days",
                value=f"{change_sign}{change} members",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @stats.command(name="voice")
    async def stats_voice(self, ctx):
        """Display voice channel usage statistics"""
        guild_id = str(ctx.guild.id)
        
        # Initialize stats for this guild if needed
        await self.initialize_guild_stats(guild_id)
        
        # Get stats from cache
        stats = self.stats_cache[guild_id]
        voice_stats = stats["voice"]
        
        # Create embed
        embed = discord.Embed(
            title=f"🎤 Voice Channel Statistics for {ctx.guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )
        
        # Add total voice time
        total_minutes = int(voice_stats["total_minutes"])
        hours = total_minutes // 60
        minutes = total_minutes % 60
        
        embed.add_field(
            name="Total Voice Time",
            value=f"{hours} hours, {minutes} minutes",
            inline=False
        )
        
        # Add top 5 channels
        channel_stats = voice_stats["by_channel"]
        if channel_stats:
            # Sort channels by usage time
            sorted_channels = sorted(channel_stats.items(), key=lambda x: x[1], reverse=True)[:5]
            
            channels_text = ""
            for channel_id, minutes in sorted_channels:
                channel = ctx.guild.get_channel(int(channel_id))
                channel_name = channel.name if channel else f"Unknown ({channel_id})"
                hours = int(minutes) // 60
                mins = int(minutes) % 60
                channels_text += f"{channel_name}: {hours}h {mins}m\n"
            
            embed.add_field(
                name="Top Voice Channels",
                value=channels_text or "No data",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @stats.command(name="reset")
    @commands.has_permissions(administrator=True)
    async def stats_reset(self, ctx):
        """Reset all statistics for this server (Admin only)"""
        guild_id = str(ctx.guild.id)
        
        # Confirm with user
        confirm_msg = await ctx.send("⚠️ Are you sure you want to reset all statistics? This cannot be undone. React with ✅ to confirm.")
        await confirm_msg.add_reaction("✅")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id
        
        try:
            # Wait for confirmation (30 seconds timeout)
            await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            # Reset stats in cache
            if guild_id in self.stats_cache:
                del self.stats_cache[guild_id]
            
            # Reset stats in database
            await db.delete_guild_stats(guild_id)
            
            # Re-initialize stats
            await self.initialize_guild_stats(guild_id)
            
            await ctx.send("✅ All statistics have been reset.")
            
        except asyncio.TimeoutError:
            await ctx.send("❌ Reset cancelled - you didn't confirm in time.")

async def setup(bot):
    await bot.add_cog(Statistics(bot))