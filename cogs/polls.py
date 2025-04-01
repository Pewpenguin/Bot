import discord
from discord.ext import commands

class Polls(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.polls = {}  # A dictionary to store active polls

    @commands.command()
    async def poll(self, ctx, question, *options: str):
        if len(options) < 2:
            await ctx.send("You need to provide at least two options for the poll.")
            return

        if len(options) > 10:
            await ctx.send("You can only provide up to 10 options for the poll.")
            return

        embed = discord.Embed(title=question, color=discord.Color.blue())
        for i, option in enumerate(options, 1):
            embed.add_field(name=f"Option {i}", value=option, inline=False)

        poll_msg = await ctx.send(embed=embed)

        for i in range(1, len(options) + 1):
            await poll_msg.add_reaction(chr(127462 + i))

        self.polls[poll_msg.id] = {
            'question': question,
            'options': options,
            'votes': {option: 0 for option in options},
            'closed': False
        }

    @commands.command()
    async def closepoll(self, ctx, poll_msg: discord.Message):
        if poll_msg.id not in self.polls:
            await ctx.send("That message is not a valid poll.")
            return

        if self.polls[poll_msg.id]['closed']:
            await ctx.send("The poll is already closed.")
            return

        self.polls[poll_msg.id]['closed'] = True
        await ctx.send("The poll is now closed. Use `!results <poll_message_link>` to view the results.")

    @commands.command()
    async def results(self, ctx, poll_msg_link: str):
        try:
            poll_msg_id = int(poll_msg_link.split('/')[-1])
        except ValueError:
            await ctx.send("Invalid poll message link.")
            return

        if poll_msg_id not in self.polls:
            await ctx.send("That message is not a valid poll.")
            return

        poll_data = self.polls[poll_msg_id]
        if not poll_data['closed']:
            await ctx.send("The poll is still open. Use `!closepoll <poll_message_link>` to close it.")
            return

        total_votes = sum(poll_data['votes'].values())
        embed = discord.Embed(title=f"Poll Results - {poll_data['question']}", color=discord.Color.green())
        for option, votes in poll_data['votes'].items():
            percentage = (votes / total_votes) * 100 if total_votes > 0 else 0
            embed.add_field(name=f"{option}", value=f"Votes: {votes} ({percentage:.1f}%)", inline=False)

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user == self.client.user:
            return

        poll_msg_id = reaction.message.id
        if poll_msg_id not in self.polls:
            return

        poll_data = self.polls[poll_msg_id]
        if poll_data['closed']:
            return

        option_emojis = [chr(127462 + i) for i in range(1, len(poll_data['options']) + 1)]
        if reaction.emoji in option_emojis:
            option_idx = ord(reaction.emoji) - 127462
            poll_data['votes'][poll_data['options'][option_idx - 1]] += 1

