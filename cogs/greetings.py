import discord
from discord.ext import commands
import aiofiles
import random
import datetime
from typing import Optional, Dict, Tuple, List

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
        
    def get_welcome_message(self, guild_id):
        if guild_id in self.welcome_channels:
            return self.welcome_channels[guild_id][1]
        return None

    def get_goodbye_message(self, guild_id):
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
        
        # Save to file
        async with aiofiles.open("data/welcome_channels.txt", mode="a") as file:
            await file.write(f"{ctx.guild.id} {new_channel.id} {message}\n")

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
        
        # Save to file
        async with aiofiles.open("data/goodbye_channels.txt", mode="a") as file:
            await file.write(f"{ctx.guild.id} {new_channel.id} {message}\n")

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
        
        # Save to file
        async with aiofiles.open("data/welcome_embeds.txt", mode="a") as file:
            await file.write(f"{ctx.guild.id} {1 if enabled else 0}\n")

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
            
        # Save to file
        async with aiofiles.open("data/join_dm.txt", mode="a") as file:
            if enabled:
                await file.write(f"{ctx.guild.id} 1 {message}\n")
            else:
                await file.write(f"{ctx.guild.id} 0\n")

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
            
            # Save to file
            async with aiofiles.open("data/member_counters.txt", mode="a") as file:
                await file.write(f"{ctx.guild.id} {channel.id} {format_string}\n")
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
        
        # Save to file
        async with aiofiles.open("data/random_welcomes.txt", mode="a") as file:
            await file.write(f"{ctx.guild.id} {message}\n")

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
        
        # Send welcome message if configured
        if guild_id in self.welcome_channels:
            channel_id = self.welcome_channels[guild_id][0]
            channel = member.guild.get_channel(channel_id)
            
            if channel:
                # Get message - either random or fixed
                if guild_id in self.welcome_messages and self.welcome_messages[guild_id]:
                    message = random.choice(self.welcome_messages[guild_id])
                else:
                    message = self.welcome_channels[guild_id][1]
                    
                formatted_message = self.format_welcome_message(message, member)
                
                # Send as embed if enabled
                if guild_id in self.welcome_embeds and self.welcome_embeds[guild_id]:
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
        
        # Send DM if enabled
        if guild_id in self.join_dm_enabled and self.join_dm_enabled[guild_id]:
            try:
                message = self.join_dm_messages.get(guild_id, f"Welcome to {member.guild.name}!")
                formatted_message = self.format_welcome_message(message, member)
                await member.send(formatted_message)
            except discord.Forbidden:
                # Can't send DM to this user
                pass
        
        # Update member counter if configured
        if guild_id in self.member_counter_channels:
            channel_id, format_string = self.member_counter_channels[guild_id]
            channel = member.guild.get_channel(channel_id)
            
            if channel:
                try:
                    await channel.edit(name=format_string.replace("{count}", str(member.guild.member_count)))
                except:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        """Handle member leave events"""
        guild_id = member.guild.id
        
        # Send goodbye message if configured
        if guild_id in self.goodbye_channels:
            channel_id = self.goodbye_channels[guild_id][0]
            channel = member.guild.get_channel(channel_id)
            
            if channel:
                message = self.goodbye_channels[guild_id][1]
                formatted_message = self.format_welcome_message(message, member)
                await channel.send(formatted_message)
        
        # Update member counter if configured
        if guild_id in self.member_counter_channels:
            channel_id, format_string = self.member_counter_channels[guild_id]
            channel = member.guild.get_channel(channel_id)
            
            if channel:
                try:
                    await channel.edit(name=format_string.replace("{count}", str(member.guild.member_count)))
                except:
                    pass