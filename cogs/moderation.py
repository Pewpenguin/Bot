import discord
import datetime
from discord.ext import commands
import asyncio
import json
from utils.database import db

class Moderation(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.muted_role_id = 0
        self._setup_collections()  
        
    def _setup_collections(self):
        """Setup MongoDB collections and Redis keys for moderation"""
        # We'll use these collections in MongoDB:
        # - warnings: Store warning records
        # - mutes: Store mute records (permanent)
        # - bans: Store ban records (permanent)
        # 
        # For temporary mutes/bans, we'll use Redis with expiration:
        # - mod:mute:{guild_id}:{user_id} -> JSON with mute info
        # - mod:ban:{guild_id}:{user_id} -> JSON with ban info  

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        # Initialize warnings in memory for quick access
        self.client.warnings[guild.id] = {}
        
        # Load warnings from MongoDB
        try:
            warnings_data = await db.find_many("warnings", {"guild_id": str(guild.id)})
            for warning in warnings_data:
                member_id = warning["member_id"]
                admin_id = warning["admin_id"]
                reason = warning["reason"]
                
                if member_id not in self.client.warnings[guild.id]:
                    self.client.warnings[guild.id][member_id] = [0, []]
                self.client.warnings[guild.id][member_id][0] += 1
                self.client.warnings[guild.id][member_id][1].append((admin_id, reason))
        except Exception as e:
            print(f"Error loading warnings for guild {guild.id}: {str(e)}")

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

        # Add the muted role
        await member.add_roles(muted_role, reason=reason)
        
        # Store mute information
        mute_data = {
            "guild_id": str(ctx.guild.id),
            "member_id": str(member.id),
            "moderator_id": str(ctx.author.id),
            "reason": reason,
            "timestamp": datetime.datetime.utcnow(),
            "duration": duration,
            "active": True
        }
        
        if duration > 0:
            # For temporary mutes, store in Redis with expiration
            redis_key = f"mod:mute:{ctx.guild.id}:{member.id}"
            await db.redis_set(redis_key, json.dumps(mute_data), ex=duration * 60)
            
            # Schedule the unmute task
            asyncio.create_task(self._schedule_unmute(ctx.guild.id, member.id, duration))
        else:
            # For permanent mutes, store in MongoDB
            await db.insert_one("mutes", mute_data)

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

        # Remove the muted role
        await member.remove_roles(muted_role, reason="Unmuted by moderator")
        
        # Update database records
        guild_id = str(ctx.guild.id)
        member_id = str(member.id)
        
        # Check if there's a temporary mute in Redis
        redis_key = f"mod:mute:{guild_id}:{member_id}"
        if await db.redis_exists(redis_key):
            await db.redis_delete(redis_key)
        
        # Update permanent mute record in MongoDB if it exists
        await db.update_one(
            "mutes",
            {"guild_id": guild_id, "member_id": member_id, "active": True},
            {"$set": {"active": False, "unmuted_by": str(ctx.author.id), "unmuted_at": datetime.datetime.utcnow()}}
        )
        
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
            # Try to DM the user
            try:
                await member.send(f"You have been banned from {ctx.guild.name} for {duration} minutes. Reason: {reason}")
            except:
                pass  # Ignore if we can't DM the user
                
            # Ban the member
            await ctx.guild.ban(member, reason=reason)
            
            # Store ban information
            ban_data = {
                "guild_id": str(ctx.guild.id),
                "member_id": str(member.id),
                "moderator_id": str(ctx.author.id),
                "reason": reason,
                "timestamp": datetime.datetime.utcnow(),
                "duration": duration,
                "active": True
            }
            
            # Store in Redis with expiration for automatic unban
            redis_key = f"mod:ban:{ctx.guild.id}:{member.id}"
            await db.redis_set(redis_key, json.dumps(ban_data), ex=duration * 60)
            
            # Also store in MongoDB for permanent record
            await db.insert_one("bans", ban_data)
            
            # Schedule the unban task
            asyncio.create_task(self._schedule_unban(ctx.guild.id, member.id, duration))
            
            await ctx.send(f"{member.mention} has been banned from the server for {duration} minutes. Reason: {reason}")

        except discord.Forbidden:
            return await ctx.send("I don't have the necessary permissions to ban members.")
            
    async def _schedule_unmute(self, guild_id, member_id, duration):
        """Schedule an unmute after the specified duration"""
        await asyncio.sleep(duration * 60)  # Sleep for the duration in seconds
        
        # Check if the mute is still active in Redis
        redis_key = f"mod:mute:{guild_id}:{member_id}"
        if not await db.redis_exists(redis_key):
            return  # Mute was manually removed
            
        # Get guild and member objects
        guild = self.client.get_guild(int(guild_id))
        if not guild:
            return
            
        member = guild.get_member(int(member_id))
        if not member:
            return
            
        # Get the muted role
        muted_role = guild.get_role(self.muted_role_id)
        if not muted_role:
            return
            
        # Remove the muted role
        try:
            await member.remove_roles(muted_role, reason="Mute duration expired")
            await db.redis_delete(redis_key)
            
            # Update MongoDB record
            await db.update_one(
                "mutes",
                {"guild_id": str(guild_id), "member_id": str(member_id), "active": True},
                {"$set": {"active": False, "unmuted_at": datetime.datetime.utcnow(), "unmuted_by": "system"}}
            )
        except Exception as e:
            print(f"Error unmuting member {member_id} in guild {guild_id}: {str(e)}")
            
    async def _schedule_unban(self, guild_id, member_id, duration):
        """Schedule an unban after the specified duration"""
        await asyncio.sleep(duration * 60)  # Sleep for the duration in seconds
        
        # Check if the ban is still active in Redis
        redis_key = f"mod:ban:{guild_id}:{member_id}"
        if not await db.redis_exists(redis_key):
            return  # Ban was manually removed
            
        # Get guild object
        guild = self.client.get_guild(int(guild_id))
        if not guild:
            return
            
        # Unban the member
        try:
            user = await self.client.fetch_user(int(member_id))
            await guild.unban(user, reason="Ban duration expired")
            await db.redis_delete(redis_key)
            
            # Update MongoDB record
            await db.update_one(
                "bans",
                {"guild_id": str(guild_id), "member_id": str(member_id), "active": True},
                {"$set": {"active": False, "unbanned_at": datetime.datetime.utcnow(), "unbanned_by": "system"}}
            )
        except Exception as e:
            print(f"Error unbanning member {member_id} in guild {guild_id}: {str(e)}")
            
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def warn(self, ctx, member: discord.Member = None, *, reason=None):
        """Warn a member in the server.
        
        Adds a warning to a member's record. Multiple warnings may lead to automatic actions.
        
        Usage:
        !warn @member [reason]
        
        Parameters:
        - member: The member to warn (mention or ID)
        - reason: Reason for the warning
        
        Example:
        !warn @User Spamming in chat
        """
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")

        if reason is None:
            return await ctx.send("Please provide a reason for warning this user.")
            
        guild_id = str(ctx.guild.id)
        member_id = str(member.id)
        admin_id = str(ctx.author.id)
        
        # Create warning document
        warning_data = {
            "guild_id": guild_id,
            "member_id": member_id,
            "admin_id": admin_id,
            "reason": reason,
            "timestamp": datetime.datetime.utcnow()
        }
        
        # Store in MongoDB
        await db.insert_one("warnings", warning_data)
        
        # Update in-memory warnings
        if guild_id not in self.client.warnings:
            self.client.warnings[guild_id] = {}
            
        if member_id not in self.client.warnings[guild_id]:
            self.client.warnings[guild_id][member_id] = [0, []]
            
        self.client.warnings[guild_id][member_id][0] += 1
        self.client.warnings[guild_id][member_id][1].append((admin_id, reason))
        
        # Get total warnings count
        warning_count = self.client.warnings[guild_id][member_id][0]
        
        await ctx.send(f"{member.mention} has been warned for: {reason}\nThis user now has {warning_count} warning(s).")
        
        # Automatic actions based on warning count
        if warning_count == 3:
            await ctx.send(f"{member.mention} has reached 3 warnings. Consider taking further action.")
        elif warning_count == 5:
            # Auto-mute after 5 warnings
            if self.muted_role_id != 0:
                muted_role = ctx.guild.get_role(self.muted_role_id)
                if muted_role:
                    await member.add_roles(muted_role, reason="Automatic mute after 5 warnings")
                    await ctx.send(f"{member.mention} has been automatically muted after receiving 5 warnings.")
                    
                    # Store mute information
                    mute_data = {
                        "guild_id": guild_id,
                        "member_id": member_id,
                        "moderator_id": "system",
                        "reason": "Automatic mute after 5 warnings",
                        "timestamp": datetime.datetime.utcnow(),
                        "duration": 0,  # Permanent
                        "active": True
                    }
                    await db.insert_one("mutes", mute_data)
    
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def warnings(self, ctx, member: discord.Member = None):
        """Check warnings for a member.
        
        Shows all warnings a member has received.
        
        Usage:
        !warnings @member
        
        Parameters:
        - member: The member to check warnings for (mention or ID)
        
        Example:
        !warnings @User
        """
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")
            
        guild_id = str(ctx.guild.id)
        member_id = str(member.id)
        
        # Get warnings from database
        warnings_data = await db.find_many("warnings", {"guild_id": guild_id, "member_id": member_id})
        
        if not warnings_data or len(warnings_data) == 0:
            return await ctx.send(f"{member.mention} has no warnings.")
            
        # Create embed
        embed = discord.Embed(
            title=f"Warnings for {member.display_name}",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
        embed.set_footer(text=f"Total Warnings: {len(warnings_data)}")
        
        # Add warnings to embed
        for i, warning in enumerate(warnings_data, 1):
            admin_id = warning.get("admin_id")
            admin = ctx.guild.get_member(int(admin_id)) if admin_id.isdigit() else None
            admin_name = admin.display_name if admin else admin_id
            
            timestamp = warning.get("timestamp", datetime.datetime.utcnow())
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(timestamp, datetime.datetime) else "Unknown"
            
            embed.add_field(
                name=f"Warning {i} - {time_str}",
                value=f"**Reason:** {warning.get('reason', 'No reason provided')}\n**Moderator:** {admin_name}",
                inline=False
            )
            
        await ctx.send(embed=embed)
        
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clearwarnings(self, ctx, member: discord.Member = None):
        """Clear all warnings for a member.
        
        Removes all warnings from a member's record.
        
        Usage:
        !clearwarnings @member
        
        Parameters:
        - member: The member to clear warnings for (mention or ID)
        
        Example:
        !clearwarnings @User
        """
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")
            
        guild_id = str(ctx.guild.id)
        member_id = str(member.id)
        
        # Delete warnings from database
        result = await db.delete_many("warnings", {"guild_id": guild_id, "member_id": member_id})
        
        # Update in-memory warnings
        if guild_id in self.client.warnings and member_id in self.client.warnings[guild_id]:
            self.client.warnings[guild_id][member_id] = [0, []]
            
        deleted_count = result.deleted_count if hasattr(result, 'deleted_count') else 0
        await ctx.send(f"Cleared {deleted_count} warnings for {member.mention}.")
        
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def removewarning(self, ctx, member: discord.Member = None, index: int = None):
        """Remove a specific warning from a member.
        
        Removes a single warning from a member's record by index.
        
        Usage:
        !removewarning @member [index]
        
        Parameters:
        - member: The member to remove a warning from (mention or ID)
        - index: The index of the warning to remove (starting from 1)
        
        Example:
        !removewarning @User 2
        """
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")
            
        if index is None or index < 1:
            return await ctx.send("Please provide a valid warning index (starting from 1).")
            
        guild_id = str(ctx.guild.id)
        member_id = str(member.id)
        
        # Get warnings from database
        warnings_data = await db.find_many("warnings", {"guild_id": guild_id, "member_id": member_id})
        
        if not warnings_data or len(warnings_data) == 0:
            return await ctx.send(f"{member.mention} has no warnings.")
            
        if index > len(warnings_data):
            return await ctx.send(f"Warning index out of range. {member.mention} has {len(warnings_data)} warnings.")
            
        # Get the warning to remove
        warning_to_remove = warnings_data[index - 1]
        
        # Delete the warning from database
        await db.delete_one("warnings", {"_id": warning_to_remove["_id"]})
        
        # Update in-memory warnings
        if guild_id in self.client.warnings and member_id in self.client.warnings[guild_id]:
            if self.client.warnings[guild_id][member_id][0] > 0:
                self.client.warnings[guild_id][member_id][0] -= 1
                if len(self.client.warnings[guild_id][member_id][1]) >= index:
                    self.client.warnings[guild_id][member_id][1].pop(index - 1)
                    
        await ctx.send(f"Removed warning {index} for {member.mention}.")
        
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def ban(self, ctx, member: discord.Member = None, *, reason=None):
        """Permanently ban a member from the server.
        
        Bans a member permanently from the server.
        The member will receive a DM with the ban reason if possible.
        
        Usage:
        !ban @member [reason]
        
        Parameters:
        - member: The member to ban (mention or ID)
        - reason: Reason for the ban
        
        Example:
        !ban @User Repeated rule violations
        """
        if member is None:
            return await ctx.send("The provided member could not be found or you forgot to provide one.")

        if reason is None:
            return await ctx.send("Please provide a reason for banning this user.")

        try:
            # Try to DM the user
            try:
                await member.send(f"You have been permanently banned from {ctx.guild.name}. Reason: {reason}")
            except:
                pass  # Ignore if we can't DM the user
                
            # Ban the member
            await ctx.guild.ban(member, reason=reason)
            
            # Store ban information
            ban_data = {
                "guild_id": str(ctx.guild.id),
                "member_id": str(member.id),
                "moderator_id": str(ctx.author.id),
                "reason": reason,
                "timestamp": datetime.datetime.utcnow(),
                "duration": 0,  # Permanent
                "active": True
            }
            
            # Store in MongoDB for permanent record
            await db.insert_one("bans", ban_data)
            
            await ctx.send(f"{member.mention} has been permanently banned from the server. Reason: {reason}")

        except discord.Forbidden:
            return await ctx.send("I don't have the necessary permissions to ban members.")
            
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def unban(self, ctx, user_id: str = None, *, reason=None):
        """Unban a user from the server.
        
        Removes a ban for a user, allowing them to rejoin the server.
        
        Usage:
        !unban [user_id] [reason]
        
        Parameters:
        - user_id: The ID of the user to unban
        - reason: Reason for the unban
        
        Example:
        !unban 123456789012345678 Appealed ban
        """
        if user_id is None or not user_id.isdigit():
            return await ctx.send("Please provide a valid user ID to unban.")

        if reason is None:
            reason = "No reason provided"

        try:
            # Fetch the user
            user = await self.client.fetch_user(int(user_id))
            if not user:
                return await ctx.send("Could not find a user with that ID.")
                
            # Check if the user is banned
            try:
                ban_entry = await ctx.guild.fetch_ban(user)
            except discord.NotFound:
                return await ctx.send(f"User {user.name}#{user.discriminator} is not banned.")
                
            # Unban the user
            await ctx.guild.unban(user, reason=reason)
            
            # Update ban record in database
            await db.update_one(
                "bans",
                {"guild_id": str(ctx.guild.id), "member_id": user_id, "active": True},
                {"$set": {"active": False, "unbanned_at": datetime.datetime.utcnow(), "unbanned_by": str(ctx.author.id), "unban_reason": reason}}
            )
            
            # Remove from Redis if it exists (for temporary bans)
            redis_key = f"mod:ban:{ctx.guild.id}:{user_id}"
            if await db.redis_exists(redis_key):
                await db.redis_delete(redis_key)
                
            await ctx.send(f"Unbanned {user.name}#{user.discriminator} ({user_id}). Reason: {reason}")

        except discord.NotFound:
            return await ctx.send("Could not find a user with that ID.")
        except discord.Forbidden:
            return await ctx.send("I don't have the necessary permissions to unban members.")
        except Exception as e:
            return await ctx.send(f"An error occurred: {str(e)}")
            
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setmuterole(self, ctx, role_id: int = None):
        """Set the role to use for muting members.
        
        Sets the role that will be applied when muting members.
        
        Usage:
        !setmuterole [role_id]
        
        Parameters:
        - role_id: The ID of the role to use for mutes
        
        Example:
        !setmuterole 123456789012345678
        """
        if role_id is None:
            return await ctx.send("Please provide a valid role ID.")
            
        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.send("Could not find a role with that ID.")
            
        self.muted_role_id = role_id
        
        # Store the muted role ID in the database
        await db.update_one(
            "guild_settings",
            {"guild_id": str(ctx.guild.id)},
            {"$set": {"muted_role_id": role_id}},
            upsert=True
        )
        
        await ctx.send(f"Set the muted role to {role.name} ({role_id}).")
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Load muted role IDs from database when bot starts"""
        for guild in self.client.guilds:
            # Load muted role ID from database
            guild_settings = await db.find_one("guild_settings", {"guild_id": str(guild.id)})
            if guild_settings and "muted_role_id" in guild_settings:
                self.muted_role_id = guild_settings["muted_role_id"]
                
        # Start background task to check for expired mutes/bans
        self.client.loop.create_task(self._check_expired_punishments())
        
    async def _check_expired_punishments(self):
        """Background task to check for expired mutes/bans"""
        await self.client.wait_until_ready()
        while not self.client.is_closed():
            try:
                # Process each guild
                for guild in self.client.guilds:
                    guild_id = str(guild.id)
                    
                    # Check for expired mutes in Redis
                    # Redis handles expiration automatically, but we need to check for any that might have expired
                    # while the bot was offline
                    mutes = await db.find_many("mutes", {"guild_id": guild_id, "active": True, "duration": {"$gt": 0}})
                    for mute in mutes:
                        member_id = mute["member_id"]
                        timestamp = mute["timestamp"]
                        duration = mute["duration"]
                        
                        # Calculate if mute should be expired
                        if isinstance(timestamp, datetime.datetime):
                            expiry_time = timestamp + datetime.timedelta(minutes=duration)
                            if datetime.datetime.utcnow() > expiry_time:
                                # Mute has expired, unmute the member
                                member = guild.get_member(int(member_id))
                                if member and self.muted_role_id != 0:
                                    muted_role = guild.get_role(self.muted_role_id)
                                    if muted_role and muted_role in member.roles:
                                        await member.remove_roles(muted_role, reason="Mute duration expired")
                                        
                                # Update database
                                await db.update_one(
                                    "mutes",
                                    {"_id": mute["_id"]},
                                    {"$set": {"active": False, "unmuted_at": datetime.datetime.utcnow(), "unmuted_by": "system"}}
                                )
                    
                    # Check for expired bans in Redis
                    bans = await db.find_many("bans", {"guild_id": guild_id, "active": True, "duration": {"$gt": 0}})
                    for ban in bans:
                        member_id = ban["member_id"]
                        timestamp = ban["timestamp"]
                        duration = ban["duration"]
                        
                        # Calculate if ban should be expired
                        if isinstance(timestamp, datetime.datetime):
                            expiry_time = timestamp + datetime.timedelta(minutes=duration)
                            if datetime.datetime.utcnow() > expiry_time:
                                # Ban has expired, unban the member
                                try:
                                    user = await self.client.fetch_user(int(member_id))
                                    await guild.unban(user, reason="Ban duration expired")
                                    
                                    # Update database
                                    await db.update_one(
                                        "bans",
                                        {"_id": ban["_id"]},
                                        {"$set": {"active": False, "unbanned_at": datetime.datetime.utcnow(), "unbanned_by": "system"}}
                                    )
                                except:
                                    pass  # User might not exist anymore or might already be unbanned
            except Exception as e:
                print(f"Error checking expired punishments: {str(e)}")
                
            # Check every 5 minutes
            await asyncio.sleep(300)