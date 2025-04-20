import discord
from discord.ext import commands
import aiofiles

class Role(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.reaction_roles = []

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        for role_id, msg_id, emoji in self.reaction_roles:
            if msg_id == payload.message_id and emoji == str(payload.emoji.name.encode("utf-8")):
                guild = self.client.get_guild(payload.guild_id)
                member = guild.get_member(payload.user_id)
                await member.add_roles(guild.get_role(role_id))
                return

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        for role_id, msg_id, emoji in self.reaction_roles:
            if msg_id == payload.message_id and emoji == str(payload.emoji.name.encode("utf-8")):
                guild = self.client.get_guild(payload.guild_id)
                member = guild.get_member(payload.user_id)
                await member.remove_roles(guild.get_role(role_id))
                return

    @commands.command()
    async def set_reaction(self, ctx, role: discord.Role = None, msg: discord.Message = None, emoji=None):
        if role is not None and msg is not None and emoji is not None:
            await msg.add_reaction(emoji)
            self.reaction_roles.append((role.id, msg.id, str(emoji.encode("utf-8"))))

            async with aiofiles.open("reaction_roles.txt", mode="a") as file:
                emoji_utf = emoji.encode("utf-8")
                await file.write(f"{role.id} {msg.id} {emoji_utf}\n")

            await ctx.send("Reaction has been set.")
        else:
            await ctx.send("Invalid arguments.")

    @commands.command()
    async def assign_role(self, ctx, role: discord.Role = None, member: discord.Member = None):
        if role is None or member is None:
            await ctx.send("Invalid arguments. Please provide both the role and the member.")
            return

        await member.add_roles(role)
        await ctx.send(f"Role '{role.name}' has been assigned to {member.mention}.")

    @commands.command()
    async def unassign_role(self, ctx, role: discord.Role = None, member: discord.Member = None):
        if role is None or member is None:
            await ctx.send("Invalid arguments. Please provide both the role and the member.")
            return

        await member.remove_roles(role)
        await ctx.send(f"Role '{role.name}' has been unassigned from {member.mention}.")

    @commands.command()
    async def create_role(self, ctx, role_name, color=None):
        # Dictionary of common color names mapped to their hex values
        color_names = {
            "red": 0xFF0000,
            "green": 0x00FF00,
            "blue": 0x0000FF,
            "yellow": 0xFFFF00,
            "purple": 0x800080,
            "orange": 0xFFA500,
            "black": 0x000000,
            "white": 0xFFFFFF,
            "pink": 0xFFC0CB,
            "cyan": 0x00FFFF,
            "gold": 0xFFD700,
            "silver": 0xC0C0C0,
            "teal": 0x008080,
            "brown": 0x8B4513,
            "gray": 0x808080
        }
        
        role_color = discord.Color.default()
        
        if color is not None:
            color = color.lower()
            # Check if it's a named color
            if color in color_names:
                role_color = discord.Color(color_names[color])
            # Check if it's a hex color code (with or without #)
            elif color.startswith('#') and len(color) == 7:
                try:
                    role_color = discord.Color(int(color[1:], 16))
                except ValueError:
                    await ctx.send(f"Invalid hex color format. Using default color instead.")
            elif len(color) == 6:
                try:
                    role_color = discord.Color(int(color, 16))
                except ValueError:
                    await ctx.send(f"Invalid hex color format. Using default color instead.")
            else:
                await ctx.send(f"Unknown color '{color}'. Using default color instead.")
                await ctx.send("Available colors: " + ", ".join(color_names.keys()) + " or use hex code like #FF0000")

        try:
            role = await ctx.guild.create_role(name=role_name, color=role_color)
            await ctx.send(f"Role '{role.name}' has been created with the specified color.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to create roles.")
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")

    @commands.command()
    async def delete_role(self, ctx, role: discord.Role = None):
        if role is None:
            await ctx.send("Please provide a valid role to delete.")
            return

        try:
            await role.delete()
            await ctx.send(f"Role '{role.name}' has been deleted.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to delete roles.")

    @commands.command()
    async def role_info(self, ctx, role: discord.Role = None):
        if role is None:
            await ctx.send("Please provide a valid role to get information.")
            return

        embed = discord.Embed(title=f"Role Information: {role.name}", color=role.color)
        embed.add_field(name="Role ID", value=role.id, inline=False)
        embed.add_field(name="Role Position", value=role.position, inline=False)
        embed.add_field(name="Members with this Role", value=len(role.members), inline=False)

        permissions = "\n".join(permission for permission, value in role.permissions if value)
        embed.add_field(name="Role Permissions", value=permissions, inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def change_permissions(self, ctx, role: discord.Role = None, **perms):
        if role is None:
            await ctx.send("Please provide a valid role to change permissions.")
            return

        try:
            await role.edit(**perms)
            await ctx.send(f"Permissions for Role '{role.name}' have been updated.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to edit roles.")