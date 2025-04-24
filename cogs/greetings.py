import discord
from discord.ext import commands
import random
import datetime
import json
from typing import Optional, Dict, Tuple, List, Any
from utils.database import db

class Greeting(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.welcome_channels = {}
        self.goodbye_channels = {}
        self.welcome_messages = {}
        self.welcome_embeds = {}
        self.join_dm_enabled = {}
        self.join_dm_messages = {}
        self.member_counter_channels = {}
        
        # Load data from database when cog is initialized
        self.client.loop.create_task(self.load_data())
        
    async def load_data(self):
        """Load greeting configuration from MongoDB"""
        try:
            # Wait until bot is ready and database is connected
            await self.client.wait_until_ready()
            if not db.connected:
                print("Database not connected. Greeting cog will use default empty settings.")
                return
                
            # Load welcome channels and messages
            try:
                welcome_data = await db.find_many("welcome_channels", {})
                for data in welcome_data:
                    guild_id = data.get("guild_id")
                    channel_id = data.get("channel_id")
                    message = data.get("message")
                    if guild_id and channel_id and message:
                        self.welcome_channels[guild_id] = (channel_id, message)
            except Exception as e:
                print(f"Error loading welcome channels: {str(e)}")
            
            # Load goodbye channels and messages
            try:
                goodbye_data = await db.find_many("goodbye_channels", {})
                for data in goodbye_data:
                    guild_id = data.get("guild_id")
                    channel_id = data.get("channel_id")
                    message = data.get("message")
                    if guild_id and channel_id and message:
                        self.goodbye_channels[guild_id] = (channel_id, message)
            except Exception as e:
                print(f"Error loading goodbye channels: {str(e)}")
            
            # Load welcome embeds settings
            try:
                embed_data = await db.find_many("welcome_embeds", {})
                for data in embed_data:
                    guild_id = data.get("guild_id")
                    enabled = data.get("enabled")
                    if guild_id is not None and enabled is not None:
                        self.welcome_embeds[guild_id] = enabled
            except Exception as e:
                print(f"Error loading welcome embeds: {str(e)}")
            
            # Load join DM settings
            try:
                join_dm_data = await db.find_many("join_dm", {})
                for data in join_dm_data:
                    guild_id = data.get("guild_id")
                    enabled = data.get("enabled")
                    message = data.get("message")
                    if guild_id is not None and enabled is not None:
                        self.join_dm_enabled[guild_id] = enabled
                        if enabled and message:
                            self.join_dm_messages[guild_id] = message
            except Exception as e:
                print(f"Error loading join DM settings: {str(e)}")
            
            # Load member counter settings
            try:
                counter_data = await db.find_many("member_counters", {})
                for data in counter_data:
                    guild_id = data.get("guild_id")
                    channel_id = data.get("channel_id")
                    format_string = data.get("format_string")
                    if guild_id and channel_id and format_string:
                        self.member_counter_channels[guild_id] = (channel_id, format_string)
            except Exception as e:
                print(f"Error loading member counters: {str(e)}")
            
            # Load random welcome messages
            try:
                random_welcome_data = await db.find_many("random_welcomes", {})
                for data in random_welcome_data:
                    guild_id = data.get("guild_id")
                    message = data.get("message")
                    if guild_id and message:
                        if guild_id not in self.welcome_messages:
                            self.welcome_messages[guild_id] = []
                        self.welcome_messages[guild_id].append(message)
            except Exception as e:
                print(f"Error loading random welcome messages: {str(e)}")
                    
            # Cache frequently accessed data in Redis
            try:
                for guild_id, (channel_id, message) in self.welcome_channels.items():
                    key = f"welcome_channel:{guild_id}"
                    value = json.dumps({"channel_id": channel_id, "message": message})
                    await db.redis_set(key, value, ex=3600)  # Cache for 1 hour
                    
                for guild_id, (channel_id, message) in self.goodbye_channels.items():
                    key = f"goodbye_channel:{guild_id}"
                    value = json.dumps({"channel_id": channel_id, "message": message})
                    await db.redis_set(key, value, ex=3600)  # Cache for 1 hour
            except Exception as e:
                print(f"Error caching data in Redis: {str(e)}")
                
        except Exception as e:
            print(f"Error loading greeting data: {str(e)}")
            print("Greeting cog will use default empty settings.")
    
    async def get_welcome_channel_from_cache(self, guild_id):
        """Try to get welcome channel info from Redis cache first"""
        try:
            key = f"welcome_channel:{guild_id}"
            cached_data = await db.redis_get(key)
            if cached_data:
                data = json.loads(cached_data)
                return data.get("channel_id"), data.get("message")
            return None
        except Exception:
            return None
    
    async def get_goodbye_channel_from_cache(self, guild_id):
        """Try to get goodbye channel info from Redis cache first"""
        try:
            key = f"goodbye_channel:{guild_id}"
            cached_data = await db.redis_get(key)
            if cached_data:
                data = json.loads(cached_data)
                return data.get("channel_id"), data.get("message")
            return None
        except Exception:
            return None
    
    def get_welcome_message(self, guild_id):
        """Get welcome message from memory cache"""
        if guild_id in self.welcome_channels:
            return self.welcome_channels[guild_id][1]
        return None

    def get_goodbye_message(self, guild_id):
        """Get goodbye message from memory cache"""
        if guild_id in self.goodbye_channels:
            return self.goodbye_channels[guild_id][1]
        return None
        
    def format_welcome_message(self, message: str, member: discord.Member) -> str:
        """Format welcome message with placeholders"""
        if not message:
            return ""
            
        placeholders = {
            "{user}": member.mention,
            "{username}": member.name,
            "{server}": member.guild.name,
            "{membercount}": str(member.guild.member_count),
            "{date}": datetime.datetime.now().strftime("%Y-%m-%d"),
            "{time}": datetime.datetime.now().strftime("%H:%M:%S")
        }
        
        for placeholder, value in placeholders.items():
            message = message.replace(placeholder, value)
            
        return message

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def set_welcome_channel(self, ctx, new_channel: discord.TextChannel = None, *, message=None):
        """Set the welcome channel and message for the server.
        
        Configures a channel where welcome messages will be sent when new members join.
        You can include placeholders in your message that will be replaced with actual values.
        
        Usage:
        !set_welcome_channel #channel Your welcome message here
        
        Example:
        !set_welcome_channel #welcome Welcome {user} to {server}! You are member #{membercount}.
        
        Placeholders:
        {user} - Mentions the new member
        {username} - The member's name without mention
        {server} - The server name
        {membercount} - Current member count
        {date} - Current date
        {time} - Current time
        """
        if new_channel is None or message is None:
            await ctx.send("Usage: !set_welcome_channel #channel Your welcome message here\n\n"
                          "Available placeholders: {user}, {username}, {server}, {membercount}, {date}, {time}")
            return
            
        self.welcome_channels[ctx.guild.id] = (new_channel.id, message)
        await ctx.send(f"Welcome channel has been set to: {new_channel.mention} with the message:\n{message}")
        
        # Save to MongoDB
        try:
            await db.update_one(
                "welcome_channels",
                {"guild_id": ctx.guild.id},
                {"$set": {"channel_id": new_channel.id, "message": message}},
                upsert=True
            )
            
            # Cache in Redis
            key = f"welcome_channel:{ctx.guild.id}"
            value = json.dumps({"channel_id": new_channel.id, "message": message})
            await db.redis_set(key, value, ex=3600)  # Cache for 1 hour
        except Exception as e:
            print(f"Error saving welcome channel: {str(e)}")
            await ctx.send("Your settings have been saved in memory, but there was an error saving to the database.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def set_goodbye_channel(self, ctx, new_channel: discord.TextChannel = None, *, message=None):
        """Set the goodbye channel and message for the server.
        
        Configures a channel where goodbye messages will be sent when members leave.
        You can include placeholders in your message that will be replaced with actual values.
        
        Usage:
        !set_goodbye_channel #channel Your goodbye message here
        
        Example:
        !set_goodbye_channel #goodbye Goodbye {username}! We'll miss you.
        
        Placeholders:
        {user} - Mentions the member
        {username} - The member's name without mention
        {server} - The server name
        {membercount} - Current member count
        {date} - Current date
        {time} - Current time
        """
        if new_channel is None or message is None:
            await ctx.send("Usage: !set_goodbye_channel #channel Your goodbye message here\n\n"
                          "Available placeholders: {user}, {username}, {server}, {membercount}, {date}, {time}")
            return
            
        self.goodbye_channels[ctx.guild.id] = (new_channel.id, message)
        await ctx.send(f"Goodbye channel has been set to: {new_channel.mention} with the message:\n{message}")
        
        # Save to MongoDB
        try:
            await db.update_one(
                "goodbye_channels",
                {"guild_id": ctx.guild.id},
                {"$set": {"channel_id": new_channel.id, "message": message}},
                upsert=True
            )
            
            # Cache in Redis
            key = f"goodbye_channel:{ctx.guild.id}"
            value = json.dumps({"channel_id": new_channel.id, "message": message})
            await db.redis_set(key, value, ex=3600)  # Cache for 1 hour
        except Exception as e:
            print(f"Error saving goodbye channel: {str(e)}")
            await ctx.send("Your settings have been saved in memory, but there was an error saving to the database.")

    @commands.command()
    async def preview_welcome(self, ctx):
        """Preview the welcome message for this server.
        
        Shows how the welcome message will appear when a new member joins.
        This is useful for testing your welcome message configuration.
        
        Usage:
        !preview_welcome
        
        The bot will display the welcome message as if you were a new member,
        including any configured embed formatting if enabled.
        """
        message = self.get_welcome_message(ctx.guild.id)
        if message is not None:
            formatted_message = self.format_welcome_message(message, ctx.author)
            
            # Check if welcome embed is enabled for this guild
            if ctx.guild.id in self.welcome_embeds and self.welcome_embeds[ctx.guild.id]:
                embed = discord.Embed(
                    title=f"Welcome to {ctx.guild.name}!",
                    description=formatted_message,
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
                embed.set_footer(text=f"Member #{ctx.guild.member_count} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"Preview of welcome message:\n{formatted_message}")
        else:
            await ctx.send("Welcome message has not been set for this server.")

    @commands.command()
    async def preview_goodbye(self, ctx):
        """Preview the goodbye message for this server.
        
        Shows how the goodbye message will appear when a member leaves.
        This is useful for testing your goodbye message configuration.
        
        Usage:
        !preview_goodbye
        
        The bot will display the goodbye message as if you were leaving,
        using your current username and server information.
        """
        message = self.get_goodbye_message(ctx.guild.id)
        if message is not None:
            formatted_message = self.format_welcome_message(message, ctx.author)
            await ctx.send(f"Preview of goodbye message:\n{formatted_message}")
        else:
            await ctx.send("Goodbye message has not been set for this server.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def toggle_welcome_embed(self, ctx, enabled: bool = None):
        """Toggle whether welcome messages should use embeds.
        
        Enables or disables the use of rich embeds for welcome messages.
        Embeds provide a more visually appealing welcome with the user's avatar.
        
        Usage:
        !toggle_welcome_embed [True/False]
        
        Examples:
        !toggle_welcome_embed True - Enable welcome embeds
        !toggle_welcome_embed False - Disable welcome embeds
        !toggle_welcome_embed - Check current status
        """
        if enabled is None:
            current = self.welcome_embeds.get(ctx.guild.id, False)
            await ctx.send(f"Welcome embeds are currently {'enabled' if current else 'disabled'}.\n"
                          f"Use `!toggle_welcome_embed True` to enable or `!toggle_welcome_embed False` to disable.")
            return
            
        self.welcome_embeds[ctx.guild.id] = enabled
        await ctx.send(f"Welcome embeds have been {'enabled' if enabled else 'disabled'}.")
        
        # Save to MongoDB
        try:
            await db.update_one(
                "welcome_embeds",
                {"guild_id": ctx.guild.id},
                {"$set": {"enabled": enabled}},
                upsert=True
            )
            
            # Cache in Redis
            key = f"welcome_embeds:{ctx.guild.id}"
            await db.redis_set(key, "1" if enabled else "0", ex=3600)  # Cache for 1 hour
        except Exception as e:
            print(f"Error saving welcome embeds setting: {str(e)}")
            await ctx.send("Your settings have been saved in memory, but there was an error saving to the database.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def set_join_dm(self, ctx, enabled: bool = None, *, message=None):
        """Set whether to send a DM to new members and what message to send.
        
        Configures automatic direct messages sent to new members when they join.
        This can be used for welcome information, server rules, or getting started guides.
        
        Usage:
        !set_join_dm [True/False] [message]
        
        Examples:
        !set_join_dm True Welcome to our server! Check out #rules to get started.
        !set_join_dm False - Disable join DMs
        !set_join_dm - Check current status
        
        The same placeholders as welcome messages can be used: {user}, {username}, {server}, etc.
        """
        if enabled is None:
            current = self.join_dm_enabled.get(ctx.guild.id, False)
            await ctx.send(f"Join DMs are currently {'enabled' if current else 'disabled'}.\n"
                          f"Use `!set_join_dm True Your message here` to enable with a custom message.\n"
                          f"Use `!set_join_dm False` to disable.")
            return
            
        if enabled and message is None:
            await ctx.send("Please provide a message to send to new members.")
            return
            
        self.join_dm_enabled[ctx.guild.id] = enabled
        if enabled:
            self.join_dm_messages[ctx.guild.id] = message
            await ctx.send(f"Join DMs have been enabled with the message:\n{message}")
        else:
            await ctx.send("Join DMs have been disabled.")
            
        # Save to MongoDB
        try:
            data = {"enabled": enabled}
            if enabled:
                data["message"] = message
                
            await db.update_one(
                "join_dm",
                {"guild_id": ctx.guild.id},
                {"$set": data},
                upsert=True
            )
            
            # Cache in Redis
            key = f"join_dm:{ctx.guild.id}"
            value = json.dumps({"enabled": enabled, "message": message if enabled else ""})
            await db.redis_set(key, value, ex=3600)  # Cache for 1 hour
        except Exception as e:
            print(f"Error saving join DM settings: {str(e)}")
            await ctx.send("Your settings have been saved in memory, but there was an error saving to the database.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def set_member_counter(self, ctx, channel: discord.VoiceChannel = None, *, format_string="Members: {count}"):
        """Set a voice channel to display the current member count"""
        if channel is None:
            await ctx.send("Please provide a voice channel to use as a member counter.")
            return
            
        self.member_counter_channels[ctx.guild.id] = (channel.id, format_string)
        
        # Update the channel name immediately
        try:
            await channel.edit(name=format_string.replace("{count}", str(ctx.guild.member_count)))
            await ctx.send(f"Member counter has been set to {channel.mention} with format: {format_string}")
            
            # Save to MongoDB
            try:
                await db.update_one(
                    "member_counters",
                    {"guild_id": ctx.guild.id},
                    {"$set": {"channel_id": channel.id, "format_string": format_string}},
                    upsert=True
                )
                
                # Cache in Redis
                key = f"member_counter:{ctx.guild.id}"
                value = json.dumps({"channel_id": channel.id, "format_string": format_string})
                await db.redis_set(key, value, ex=3600)  # Cache for 1 hour
            except Exception as e:
                print(f"Error saving member counter: {str(e)}")
                await ctx.send("Your settings have been saved in memory, but there was an error saving to the database.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to edit that channel.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def add_random_welcome(self, ctx, *, message):
        """Add a random welcome message to the pool for this server"""
        if ctx.guild.id not in self.welcome_messages:
            self.welcome_messages[ctx.guild.id] = []
            
        self.welcome_messages[ctx.guild.id].append(message)
        await ctx.send(f"Added new random welcome message:\n{message}")
        
        # Save to MongoDB
        try:
            await db.insert_one(
                "random_welcomes",
                {"guild_id": ctx.guild.id, "message": message}
            )
            
            # Update Redis cache
            key = f"random_welcomes:{ctx.guild.id}"
            messages = await db.redis_lrange(key, 0, -1)
            if not messages:
                # If not in cache, add this message
                await db.redis_rpush(key, message)
                await db.redis_expire(key, 3600)  # Cache for 1 hour
            else:
                # Add to existing cache
                await db.redis_rpush(key, message)
                await db.redis_expire(key, 3600)  # Refresh expiration
        except Exception as e:
            print(f"Error saving random welcome message: {str(e)}")
            await ctx.send("Your message has been saved in memory, but there was an error saving to the database.")
            
            # Still add to memory cache even if database fails
            if ctx.guild.id not in self.welcome_messages:
                self.welcome_messages[ctx.guild.id] = []
            self.welcome_messages[ctx.guild.id].append(message)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def list_welcome_messages(self, ctx):
        """List all random welcome messages for this server"""
        if ctx.guild.id not in self.welcome_messages or not self.welcome_messages[ctx.guild.id]:
            await ctx.send("No random welcome messages have been set for this server.")
            return
            
        messages = self.welcome_messages[ctx.guild.id]
        embed = discord.Embed(title="Random Welcome Messages", color=discord.Color.blue())
        
        for i, msg in enumerate(messages, 1):
            embed.add_field(name=f"Message {i}", value=msg, inline=False)
            
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle member join events"""
        guild_id = member.guild.id
        
        # Try to get welcome channel info from Redis cache first
        welcome_channel_info = None
        if db.connected:
            welcome_channel_info = await self.get_welcome_channel_from_cache(guild_id)
        
        # If not in Redis, use memory cache
        if welcome_channel_info:
            channel_id, welcome_message = welcome_channel_info
        elif guild_id in self.welcome_channels:
            channel_id = self.welcome_channels[guild_id][0]
            welcome_message = self.welcome_channels[guild_id][1]
        else:
            # No welcome channel configured
            channel_id = None
            welcome_message = None
        
        # Send welcome message if configured
        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            
            if channel:
                # Try to get random welcome messages from Redis
                random_messages = []
                if db.connected:
                    key = f"random_welcomes:{guild_id}"
                    random_messages = await db.redis_lrange(key, 0, -1)
                
                # If not in Redis, use memory cache
                if not random_messages and guild_id in self.welcome_messages and self.welcome_messages[guild_id]:
                    random_messages = self.welcome_messages[guild_id]
                
                # Get message - either random or fixed
                if random_messages:
                    message = random.choice(random_messages)
                else:
                    message = welcome_message
                    
                formatted_message = self.format_welcome_message(message, member)
                
                # Check if welcome embed is enabled from Redis
                use_embed = False
                if db.connected:
                    key = f"welcome_embeds:{guild_id}"
                    embed_enabled = await db.redis_get(key)
                    if embed_enabled is not None:
                        use_embed = embed_enabled == "1"
                    else:
                        use_embed = guild_id in self.welcome_embeds and self.welcome_embeds[guild_id]
                else:
                    use_embed = guild_id in self.welcome_embeds and self.welcome_embeds[guild_id]
                
                # Send as embed if enabled
                if use_embed:
                    embed = discord.Embed(
                        title=f"Welcome to {member.guild.name}!",
                        description=formatted_message,
                        color=discord.Color.green()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.set_footer(text=f"Member #{member.guild.member_count} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
                    await channel.send(embed=embed)
                else:
                    await channel.send(formatted_message)
        
        # Check if join DM is enabled from Redis first
        join_dm_enabled = False
        join_dm_message = None
        
        if db.connected:
            key = f"join_dm:{guild_id}"
            cached_data = await db.redis_get(key)
            if cached_data:
                try:
                    data = json.loads(cached_data)
                    join_dm_enabled = data.get("enabled", False)
                    join_dm_message = data.get("message", "")
                except:
                    pass
        
        # If not in Redis, use memory cache
        if join_dm_message is None:
            join_dm_enabled = guild_id in self.join_dm_enabled and self.join_dm_enabled[guild_id]
            if join_dm_enabled:
                join_dm_message = self.join_dm_messages.get(guild_id, f"Welcome to {member.guild.name}!")
        
        # Send DM if enabled
        if join_dm_enabled and join_dm_message:
            try:
                formatted_message = self.format_welcome_message(join_dm_message, member)
                await member.send(formatted_message)
            except discord.Forbidden:
                # Can't send DM to this user
                pass
        
        # Try to get member counter info from Redis first
        member_counter_info = None
        if db.connected:
            key = f"member_counter:{guild_id}"
            cached_data = await db.redis_get(key)
            if cached_data:
                try:
                    data = json.loads(cached_data)
                    channel_id = data.get("channel_id")
                    format_string = data.get("format_string")
                    if channel_id and format_string:
                        member_counter_info = (channel_id, format_string)
                except:
                    pass
        
        # If not in Redis, use memory cache
        if not member_counter_info and guild_id in self.member_counter_channels:
            member_counter_info = self.member_counter_channels[guild_id]
        
        # Update member counter if configured
        if member_counter_info:
            channel_id, format_string = member_counter_info
            channel = member.guild.get_channel(int(channel_id))
            
            if channel:
                try:
                    await channel.edit(name=format_string.replace("{count}", str(member.guild.member_count)))
                except:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Handle member leave events"""
        guild_id = member.guild.id
        
        # Try to get goodbye channel info from Redis cache first
        goodbye_channel_info = None
        if db.connected:
            goodbye_channel_info = await self.get_goodbye_channel_from_cache(guild_id)
        
        # If not in Redis, use memory cache
        if goodbye_channel_info:
            channel_id, goodbye_message = goodbye_channel_info
        elif guild_id in self.goodbye_channels:
            channel_id = self.goodbye_channels[guild_id][0]
            goodbye_message = self.goodbye_channels[guild_id][1]
        else:
            # No goodbye channel configured
            channel_id = None
            goodbye_message = None
        
        # Send goodbye message if configured
        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            
            if channel:
                formatted_message = self.format_welcome_message(goodbye_message, member)
                await channel.send(formatted_message)
        
        # Try to get member counter info from Redis first
        member_counter_info = None
        if db.connected:
            key = f"member_counter:{guild_id}"
            cached_data = await db.redis_get(key)
            if cached_data:
                try:
                    data = json.loads(cached_data)
                    channel_id = data.get("channel_id")
                    format_string = data.get("format_string")
                    if channel_id and format_string:
                        member_counter_info = (channel_id, format_string)
                except:
                    pass
        
        # If not in Redis, use memory cache
        if not member_counter_info and guild_id in self.member_counter_channels:
            member_counter_info = self.member_counter_channels[guild_id]
        
        # Update member counter if configured
        if member_counter_info:
            channel_id, format_string = member_counter_info
            channel = member.guild.get_channel(int(channel_id))
            
            if channel:
                try:
                    await channel.edit(name=format_string.replace("{count}", str(member.guild.member_count)))
                except:
                    pass