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
        if color is not None:
            try:
                color = discord.Color(int(color, 16))
            except ValueError:
                color = discord.Color.default()

        try:
            role = await ctx.guild.create_role(name=role_name, color=color)
            await ctx.send(f"Role '{role.name}' has been created.")
        except discord.Forbidden:
            await ctx.send("I don't have the necessary permissions to create roles.")

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