import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, client):
        self.client = client

    async def get_help_embed(self):
        em = discord.Embed(title="Help!", description="", color=discord.Color.green())

        # Iterate through each cog and retrieve its commands
        for cog in self.client.cogs.values():
            commands_list = []

            # Skip hidden cogs (e.g., those without commands)
            if len(cog.get_commands()) == 0:
                continue

            # Add cog name as the title and its commands to the embed
            em.add_field(name=f"__{cog.qualified_name}__", value="\n".join(f"**{self.client.command_prefix}{cmd.name}** : {cmd.help}" for cmd in cog.get_commands()), inline=False)

        avatar_url = self.client.user.avatar.url if self.client.user.avatar else None
        em.set_thumbnail(url=avatar_url)
        em.set_footer(text="Thanks for using me!")
        return em

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.client.user.mentioned_in(message):
            em = await self.get_help_embed()
            await message.channel.send(embed=em)

        await self.client.process_commands(message)

    @commands.command()
    async def help(self, ctx, *, cog_name=None):
        em = await self.get_help_embed(cog_name)
        await ctx.send(embed=em)