import discord
from discord.ext import commands
from typing import Optional, List, Dict, Any

class Help(commands.Cog):
    """A comprehensive help command that displays all commands by category"""
    
    def __init__(self, client):
        self.client = client
        self.client.remove_command('help')  # Remove the default help command
        
        # Define emojis for each category
        self.category_emojis = {
            'Role': '🏷️',
            'Greeting': '👋',
            'Moderation': '🛡️',
            'Polls': '📊',
            'Music': '🎵',
            'Help': '❓'
        }
        
        # Define category descriptions
        self.category_descriptions = {
            'Role': 'Commands for managing reaction roles',
            'Greeting': 'Commands for welcome and goodbye messages',
            'Moderation': 'Commands for server moderation',
            'Polls': 'Commands for creating and managing polls',
            'Music': 'Commands for playing music in voice channels',
            'Help': 'Commands for getting help with the bot'
        }
    
    def get_command_signature(self, command):
        """Get the command signature with prefix and parameters"""
        return f'{self.client.command_prefix}{command.qualified_name} {command.signature}'
    
    def get_command_description(self, command):
        """Get the command description or help text"""
        return command.help or 'No description available'
    
    def get_cog_commands(self, cog):
        """Get all commands from a cog"""
        return [cmd for cmd in self.client.commands if cmd.cog_name == cog.qualified_name]
    
    async def create_category_embed(self, ctx, cog_name):
        """Create an embed for a specific category"""
        cog = self.client.get_cog(cog_name)
        if not cog:
            return None
            
        commands = self.get_cog_commands(cog)
        if not commands:
            return None
            
        emoji = self.category_emojis.get(cog_name, '📝')
        description = self.category_descriptions.get(cog_name, 'Commands in this category')
        
        embed = discord.Embed(
            title=f"{emoji} {cog_name} Commands",
            description=description,
            color=discord.Color.blue()
        )
        
        for cmd in commands:
            # Skip commands that the user can't run
            try:
                can_run = await cmd.can_run(ctx)
            except:
                can_run = False
                
            if not can_run:
                continue
                
            signature = self.get_command_signature(cmd)
            description = self.get_command_description(cmd)
            embed.add_field(name=signature, value=description, inline=False)
        
        return embed
    
    @commands.command(name="help", help="Shows this help message")
    async def help_command(self, ctx, *, category: Optional[str] = None):
        """Display help for all commands or a specific category.
        
        Shows a list of all available commands grouped by category,
        or detailed information about a specific category or command.
        
        Usage:
        !help
        !help [category]
        !help [command]
        
        Parameters:
        - category/command: The category or command to get help for (optional)
        
        Examples:
        !help - Show all commands
        !help Music - Show all music commands
        !help play - Show details for the play command
        """
        if category:
            # Try to match the category name (case-insensitive)
            for cog_name in self.client.cogs:
                if cog_name.lower() == category.lower():
                    embed = await self.create_category_embed(ctx, cog_name)
                    if embed:
                        return await ctx.send(embed=embed)
            
            # If no category match, try to find a command match
            for command in self.client.commands:
                if command.name.lower() == category.lower():
                    embed = discord.Embed(
                        title=f"Help: {command.name}",
                        description=self.get_command_description(command),
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Usage", value=f"`{self.get_command_signature(command)}`", inline=False)
                    
                    if command.aliases:
                        embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)
                    
                    return await ctx.send(embed=embed)
            
            # No matches found
            return await ctx.send(f"❌ No category or command found with name '{category}'")
        
        # Show main help menu with categories
        embed = discord.Embed(
            title="📚 Bot Help Menu",
            description=f"Use `{self.client.command_prefix}help <category>` to view commands in a specific category.",
            color=discord.Color.blue()
        )
        
        # Add all categories
        for cog_name in sorted(self.client.cogs):
            cog = self.client.get_cog(cog_name)
            commands = self.get_cog_commands(cog)
            
            # Skip empty categories
            if not commands:
                continue
                
            emoji = self.category_emojis.get(cog_name, '📝')
            description = self.category_descriptions.get(cog_name, 'Commands in this category')
            
            # Count commands user can run
            runnable_commands = 0
            for cmd in commands:
                try:
                    can_run = await cmd.can_run(ctx)
                    if can_run:
                        runnable_commands += 1
                except:
                    pass
            
            if runnable_commands > 0:
                embed.add_field(
                    name=f"{emoji} {cog_name}",
                    value=f"{description}\n`{self.client.command_prefix}help {cog_name.lower()}`",
                    inline=True
                )
        
        # Add footer with command count
        total_commands = len(self.client.commands)
        embed.set_footer(text=f"Total commands: {total_commands} | Bot prefix: {self.client.command_prefix}")
        
        await ctx.send(embed=embed)

# Setup function for the cog
async def setup(client):
    await client.add_cog(Help(client))