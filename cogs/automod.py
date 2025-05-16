import discord
from discord.ext import commands, tasks
import asyncio
import re
import json
from datetime import datetime, timedelta

from utils.database import db

class AutoMod(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.spam_trackers = {}
        self.mention_trackers = {}
        self.raid_alerts = {}
        self.check_mutes.start() 

    async def get_automod_config(self, guild_id: int):
        """Retrieve automod configuration for a guild."""
        config = await db.find_one("automod_config", {"guild_id": guild_id})
        if not config:
            return {
                "guild_id": guild_id,
                "enabled": False,
                "banned_words": [],
                "spam_threshold": {"count": 5, "seconds": 10, "action": "warn"},
                "mention_threshold": {"count": 5, "seconds": 10, "action": "warn"},
                "raid_threshold": {"joins": 5, "seconds": 10, "action": "kick"},
                "log_channel_id": None,
                "mute_duration_minutes": 30 
            }
        return config

    async def update_automod_config(self, guild_id: int, new_config: dict):
        """Update automod configuration for a guild."""
        await db.update_one("automod_config", {"guild_id": guild_id}, {"$set": new_config}, upsert=True)

    async def log_action(self, guild: discord.Guild, action: str, user: discord.Member, reason: str):
        config = await self.get_automod_config(guild.id)
        log_channel_id = config.get("log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title="AutoMod Action", color=discord.Color.orange(), timestamp=datetime.utcnow())
                embed.add_field(name="Action Taken", value=action, inline=False)
                embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=False)
                embed.add_field(name="Reason", value=reason, inline=False)
                try:
                    await log_channel.send(embed=embed)
                except discord.Forbidden:
                    print(f"[AutoMod] Missing permissions to send log message in {log_channel.name} ({guild.name})")
                except Exception as e:
                    print(f"[AutoMod] Error sending log message: {e}")

    async def perform_action(self, message: discord.Message, action_type: str, reason: str):
        guild = message.guild
        member = message.author

        if action_type == "warn":
            try:
                await member.send(f"You were warned in {guild.name} for: {reason}")
                await message.channel.send(f"{member.mention}, you have been warned for: {reason}", delete_after=10)
                await self.log_action(guild, "Warned User", member, reason)
            except discord.Forbidden:
                await message.channel.send(f"Could not DM {member.mention}. They have been warned for: {reason}", delete_after=10)
                await self.log_action(guild, "Warned User (DM Failed)", member, reason)
        elif action_type == "delete":
            try:
                await message.delete()
                await message.channel.send(f"Message from {member.mention} deleted due to: {reason}", delete_after=10)
                await self.log_action(guild, "Deleted Message", member, reason)
            except discord.Forbidden:
                await self.log_action(guild, "Delete Message Failed (Permissions)", member, reason)
            except discord.NotFound:
                pass 
        elif action_type == "mute":
            config = await self.get_automod_config(guild.id)
            mute_duration_minutes = config.get("mute_duration_minutes", 30) 

            try:
                muted_role = discord.utils.get(guild.roles, name="Muted")
                if not muted_role:
                    try:
                        muted_role = await guild.create_role(name="Muted", reason="AutoMod Mute Role")
                        for channel in guild.text_channels:
                            await channel.set_permissions(muted_role, send_messages=False, read_messages=True)
                        for channel in guild.voice_channels:
                            await channel.set_permissions(muted_role, speak=False, connect=True)
                        await self.log_action(guild, "Created Muted Role", guild.me, "Muted role created for AutoMod.")
                    except discord.Forbidden:
                        await self.log_action(guild, "Mute Failed (Cannot Create Muted Role)", member, reason)
                        return
                
                if muted_role in member.roles:
                    await self.log_action(guild, "Mute Attempt (Already Muted)", member, reason)
                    return

                await member.add_roles(muted_role, reason=f"AutoMod: {reason}")
                
                mute_end_time = None
                if mute_duration_minutes > 0:
                    mute_end_time = datetime.utcnow() + timedelta(minutes=mute_duration_minutes)
                    mute_record = {
                        "guild_id": str(guild.id),
                        "user_id": str(member.id),
                        "mute_end_time": mute_end_time.isoformat(),
                        "reason": reason,
                        "muted_by_automod": True
                    }
                    redis_key = f"automod:mute:{guild.id}:{member.id}"
                    await db.redis_set(redis_key, json.dumps(mute_record), ex=mute_duration_minutes * 60)
                    await message.channel.send(f"{member.mention} has been muted for {mute_duration_minutes} minutes for: {reason}", delete_after=10)
                    await self.log_action(guild, f"Muted User ({mute_duration_minutes} mins)", member, reason)
                else: 
                    permanent_mute_record = {
                        "guild_id": str(guild.id),
                        "user_id": str(member.id),
                        "reason": reason,
                        "timestamp": datetime.utcnow().isoformat(),
                        "muted_by_automod": True,
                        "active": True
                    }
                    await db.insert_one("mutes", permanent_mute_record) 
                    await message.channel.send(f"{member.mention} has been permanently muted for: {reason}", delete_after=10)
                    await self.log_action(guild, "Muted User (Permanent)", member, reason)

            except discord.Forbidden:
                await self.log_action(guild, "Mute Failed (Permissions)", member, reason)
            except Exception as e:
                await self.log_action(guild, "Mute Failed (Error)", member, f"{reason} - Error: {e}")
                print(f"[AutoMod] Error during mute action: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await self.get_automod_config(message.guild.id)
        if not config.get("enabled", False):
            return

        banned_words = config.get("banned_words", [])
        if banned_words:
            for word in banned_words:
                if re.search(rf'\b{re.escape(word)}\b', message.content, re.IGNORECASE):
                    action = config.get("banned_word_action", "delete") # Default to delete
                    await self.perform_action(message, action, f"Use of banned word/phrase: '{word}'")
                    if action == "delete": 
                        return 
                    break

        spam_config = config.get("spam_threshold", {"count": 5, "seconds": 10, "action": "warn"})
        user_id = message.author.id
        guild_id = message.guild.id
        current_time = datetime.utcnow()

        if guild_id not in self.spam_trackers:
            self.spam_trackers[guild_id] = {}
        if user_id not in self.spam_trackers[guild_id]:
            self.spam_trackers[guild_id][user_id] = []

        self.spam_trackers[guild_id][user_id] = [
            ts for ts in self.spam_trackers[guild_id][user_id]
            if current_time - ts < timedelta(seconds=spam_config["seconds"])
        ]
        self.spam_trackers[guild_id][user_id].append(current_time)

        if len(self.spam_trackers[guild_id][user_id]) >= spam_config["count"]:
            await self.perform_action(message, spam_config["action"], "Spamming messages")
            self.spam_trackers[guild_id][user_id] = []
            if spam_config["action"] == "delete":
                return

        mention_config = config.get("mention_threshold", {"count": 5, "seconds": 10, "action": "warn"})
        num_mentions = len(message.mentions) + len(message.role_mentions)

        if num_mentions > 0:
            if guild_id not in self.mention_trackers:
                self.mention_trackers[guild_id] = {}
            if user_id not in self.mention_trackers[guild_id]:
                self.mention_trackers[guild_id][user_id] = {"timestamps": [], "count": 0}

            self.mention_trackers[guild_id][user_id]["timestamps"] = [
                ts for ts in self.mention_trackers[guild_id][user_id]["timestamps"]
                if current_time - ts < timedelta(seconds=mention_config["seconds"])
            ]
            for _ in range(num_mentions):
                 self.mention_trackers[guild_id][user_id]["timestamps"].append(current_time)

            if len(self.mention_trackers[guild_id][user_id]["timestamps"]) >= mention_config["count"]:
                action_to_perform = mention_config["action"]
                await self.perform_action(message, action_to_perform, "Excessive mentions")
                self.mention_trackers[guild_id][user_id]["timestamps"] = [] 
                # If action was mute, message is already handled by perform_action.
                # If action was delete, we need to return to prevent further processing on a deleted message.
                if action_to_perform == "delete":
                    return
                # For 'warn', we don't need to return, other checks might still apply or message might be kept.

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        config = await self.get_automod_config(guild.id)
        if not config.get("enabled", False):
            return

        raid_config = config.get("raid_threshold", {"joins": 5, "seconds": 10, "action": "kick"})
        current_time = datetime.now(datetime.timezone.utc)

        if guild.id not in self.raid_alerts:
            self.raid_alerts[guild.id] = []

        self.raid_alerts[guild.id] = [
            ts for ts in self.raid_alerts[guild.id]
            if current_time - ts < timedelta(seconds=raid_config["seconds"])
        ]
        self.raid_alerts[guild.id].append(current_time)

        if len(self.raid_alerts[guild.id]) >= raid_config["joins"]:
            await self.log_action(guild, "Raid Detected", member, f"{len(self.raid_alerts[guild.id])} joins in {raid_config['seconds']}s")
            self.raid_alerts[guild.id] = [] 

            if raid_config["action"] == "kick":
                try:
                    await member.kick(reason="AutoMod: Raid Protection")
                    await self.log_action(guild, "Kicked Member (Raid)", member, "Part of detected raid")
                except discord.Forbidden:
                    await self.log_action(guild, "Kick Failed (Raid - Permissions)", member, "Part of detected raid")
            elif raid_config["action"] == "ban": 
                try:
                    await member.ban(reason="AutoMod: Raid Protection", delete_message_days=0)
                    await self.log_action(guild, "Banned Member (Raid)", member, "Part of detected raid")
                except discord.Forbidden:
                    await self.log_action(guild, "Ban Failed (Raid - Permissions)", member, "Part of detected raid")

    @commands.group(name="automod", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def automod_group(self, ctx: commands.Context):
        """Manage AutoMod settings for this server."""
        await ctx.send_help(ctx.command)

    @automod_group.command(name="toggle")
    @commands.has_permissions(administrator=True)
    async def automod_toggle(self, ctx: commands.Context, on_off: bool):
        """Enable or disable AutoMod for this server."""
        config = await self.get_automod_config(ctx.guild.id)
        config["enabled"] = on_off
        await self.update_automod_config(ctx.guild.id, config)
        status = "enabled" if on_off else "disabled"
        await ctx.send(f"AutoMod has been {status} for this server.")

    @automod_group.command(name="config")
    @commands.has_permissions(administrator=True)
    async def automod_config_view(self, ctx: commands.Context):
        """View the current AutoMod configuration."""
        config = await self.get_automod_config(ctx.guild.id)
        embed = discord.Embed(title=f"AutoMod Configuration for {ctx.guild.name}", color=discord.Color.blue())
        embed.add_field(name="Status", value="Enabled" if config.get("enabled") else "Disabled", inline=False)
        embed.add_field(name="Log Channel", value=f"<#{config.get('log_channel_id')}>" if config.get('log_channel_id') else "Not Set", inline=False)
        
        spam = config.get("spam_threshold", {})
        embed.add_field(name="Spam Detection", value=f"Action: {spam.get('action', 'N/A')}, Threshold: {spam.get('count', 'N/A')} msgs / {spam.get('seconds', 'N/A')}s", inline=False)
        
        mention = config.get("mention_threshold", {})
        embed.add_field(name="Mention Spam", value=f"Action: {mention.get('action', 'N/A')}, Threshold: {mention.get('count', 'N/A')} mentions / {mention.get('seconds', 'N/A')}s", inline=False)
        
        raid = config.get("raid_threshold", {})
        embed.add_field(name="Raid Protection", value=f"Action: {raid.get('action', 'N/A')}, Joins: {raid.get('joins', 'N/A')} / {raid.get('seconds', 'N/A')}s", inline=False)
        embed.add_field(name="Default Mute Duration", value=f"{config.get('mute_duration_minutes', 30)} minutes", inline=False)
        
        banned_words_list = config.get("banned_words", [])
        banned_words_display = ", ".join(banned_words_list) if banned_words_list else "None"
        if len(banned_words_display) > 1000:
            banned_words_display = banned_words_display[:1000] + "... (list too long)"
        embed.add_field(name="Banned Words", value=banned_words_display, inline=False)
        
        await ctx.send(embed=embed)

    @automod_group.command(name="logchannel")
    @commands.has_permissions(administrator=True)
    async def automod_logchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel where AutoMod actions will be logged. Provide no channel to disable."""
        config = await self.get_automod_config(ctx.guild.id)
        if channel:
            config["log_channel_id"] = channel.id
            await self.update_automod_config(ctx.guild.id, config)
            await ctx.send(f"AutoMod log channel set to {channel.mention}.")
        else:
            config["log_channel_id"] = None
            await self.update_automod_config(ctx.guild.id, config)
            await ctx.send("AutoMod logging disabled.")

    @automod_group.command(name="addbannedword")
    @commands.has_permissions(administrator=True)
    async def automod_addbannedword(self, ctx: commands.Context, *, word: str):
        """Add a word or phrase to the banned list (case-insensitive)."""
        config = await self.get_automod_config(ctx.guild.id)
        word = word.lower()
        if word not in config["banned_words"]:
            config["banned_words"].append(word)
            await self.update_automod_config(ctx.guild.id, config)
            await ctx.send(f"Added '{word}' to the banned words list.")
        else:
            await ctx.send(f"'{word}' is already in the banned words list.")

    @automod_group.command(name="removebannedword")
    @commands.has_permissions(administrator=True)
    async def automod_removebannedword(self, ctx: commands.Context, *, word: str):
        """Remove a word or phrase from the banned list."""
        config = await self.get_automod_config(ctx.guild.id)
        word = word.lower()
        if word in config["banned_words"]:
            config["banned_words"].remove(word)
            await self.update_automod_config(ctx.guild.id, config)
            await ctx.send(f"Removed '{word}' from the banned words list.")
        else:
            await ctx.send(f"'{word}' is not in the banned words list.")

    @automod_group.command(name="setspam")
    @commands.has_permissions(administrator=True)
    async def automod_setspam(self, ctx: commands.Context, count: int, seconds: int, action: str):
        """Set spam detection parameters. Actions: warn, delete, mute."""
        if action.lower() not in ["warn", "delete", "mute"]:
            return await ctx.send("Invalid action. Choose from: warn, delete, mute.")
        config = await self.get_automod_config(ctx.guild.id)
        config["spam_threshold"] = {"count": count, "seconds": seconds, "action": action.lower()}
        await self.update_automod_config(ctx.guild.id, config)
        await ctx.send(f"Spam detection set to: {count} messages in {seconds}s, action: {action.lower()}.")

    @automod_group.command(name="setmention")
    @commands.has_permissions(administrator=True)
    async def automod_setmention(self, ctx: commands.Context, count: int, seconds: int, action: str):
        """Set excessive mention parameters. Actions: warn, delete, mute."""
        if action.lower() not in ["warn", "delete", "mute"]:
            return await ctx.send("Invalid action. Choose from: warn, delete, mute.")
        config = await self.get_automod_config(ctx.guild.id)
        config["mention_threshold"] = {"count": count, "seconds": seconds, "action": action.lower()}
        await self.update_automod_config(ctx.guild.id, config)
        await ctx.send(f"Excessive mention detection set to: {count} mentions in {seconds}s, action: {action.lower()}.")

    @automod_group.command(name="setraid")
    @commands.has_permissions(administrator=True)
    async def automod_setraid(self, ctx: commands.Context, joins: int, seconds: int, action: str):
        """Set raid protection parameters. Actions: kick, ban, warn."""
        if action.lower() not in ["kick", "ban", "warn"]:
            return await ctx.send("Invalid action. Choose from: kick, ban, warn.")
        config = await self.get_automod_config(ctx.guild.id)
        config["raid_threshold"] = {"joins": joins, "seconds": seconds, "action": action.lower()}
        await self.update_automod_config(ctx.guild.id, config)
        await ctx.send(f"Raid protection set to: {joins} joins in {seconds}s, action: {action.lower()}.")

    @automod_group.command(name="setmuteduration")
    @commands.has_permissions(administrator=True)
    async def automod_setmuteduration(self, ctx: commands.Context, minutes: int):
        """Set the default duration for mutes triggered by AutoMod (in minutes). Set to 0 for permanent.
        Example: !automod setmuteduration 60 (sets to 1 hour)
        Example: !automod setmuteduration 0 (sets to permanent)
        """
        if minutes < 0:
            return await ctx.send("Mute duration cannot be negative. Set to 0 for permanent mutes.")
        config = await self.get_automod_config(ctx.guild.id)
        config["mute_duration_minutes"] = minutes
        await self.update_automod_config(ctx.guild.id, config)
        if minutes == 0:
            await ctx.send(f"AutoMod default mute duration set to: Permanent.")
        else:
            await ctx.send(f"AutoMod default mute duration set to: {minutes} minutes.")

    @tasks.loop(minutes=1)
    async def check_mutes(self):
        """Periodically checks Redis for expired mutes and unmutes members.
           Also handles permanent mutes stored in 'mutes' collection if needed, though primary focus is Redis temp mutes.
        """
        try:
            keys = await db.redis_keys("automod:mute:*:*")
            for key in keys:
                try:
                    guild_id_str, user_id_str = key.split(':')[2], key.split(':')[3]
                    guild_id = int(guild_id_str)
                    user_id = int(user_id_str)

                    mute_data_json = await db.redis_get(key)
                    if not mute_data_json:
                        continue 
                    
                    mute_data = json.loads(mute_data_json)
                    mute_end_time_iso = mute_data.get("mute_end_time")
                    if not mute_end_time_iso:
                        await db.redis_delete(key) 
                        continue

                    mute_end_time = datetime.fromisoformat(mute_end_time_iso)

                    if datetime.utcnow() >= mute_end_time:
                        guild = self.client.get_guild(guild_id)
                        if not guild:
                            await db.redis_delete(key) 
                            continue
                        
                        member = guild.get_member(user_id)
                        if not member:
                            await db.redis_delete(key) 
                            continue
                        
                        muted_role = discord.utils.get(guild.roles, name="Muted")
                        if muted_role and muted_role in member.roles:
                            try:
                                await member.remove_roles(muted_role, reason="AutoMod: Mute expired")
                                await self.log_action(guild, "Unmuted User (Auto)", member, "Mute duration expired")
                            except discord.Forbidden:
                                await self.log_action(guild, "Unmute Failed (Auto - Permissions)", member, "Mute duration expired")
                            except Exception as e:
                                print(f"[AutoMod Check Mutes] Error unmuting {member.id} in {guild.id}: {e}")
                        await db.redis_delete(key) # Remove from Redis after processing

                except Exception as e:
                    print(f"[AutoMod Check Mutes] Error processing key {key}: {e}")
                    await db.redis_delete(key)
        except Exception as e:
            print(f"[AutoMod Check Mutes] Error fetching Redis keys: {e}")

    @check_mutes.before_loop
    async def before_check_mutes(self):
        await self.client.wait_until_ready()
        print("[AutoMod] Mute check loop is ready.")

async def setup(client):
    await client.add_cog(AutoMod(client))