import discord
from discord.ext import commands
import re

class Polls(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.polls = {}  # A dictionary to store active polls

    @commands.command()
    async def poll(self, ctx, question=None, *options: str):
        # Check if question is provided
        if question is None:
            await ctx.send("❌ Error: You need to provide a question for the poll.\nUsage: `!poll Your question here" "Option 1" "Option 2")
            return
            
        if len(options) < 2:
            await ctx.send("❌ Error: You need to provide at least two options for the poll.")
            return

        if len(options) > 10:
            await ctx.send("❌ Error: You can only provide up to 10 options for the poll.")
            return

        # Create a more descriptive embed
        embed = discord.Embed(
            title=f"📊 Poll: {question}", 
            description="React with the corresponding letter to vote!", 
            color=discord.Color.blue()
        )
        
        # Add options with emoji indicators
        for i, option in enumerate(options, 1):
            emoji = chr(127462 + i)  # 🇦, 🇧, 🇨, etc.
            embed.add_field(name=f"{emoji} Option {i}", value=option, inline=False)
            
        embed.set_footer(text=f"Poll created by {ctx.author.display_name} • Use !closepoll to end the poll")

        try:
            poll_msg = await ctx.send(embed=embed)

            # Add reactions
            for i in range(1, len(options) + 1):
                await poll_msg.add_reaction(chr(127462 + i))

            # Store poll data
            self.polls[poll_msg.id] = {
                'question': question,
                'options': options,
                'votes': {option: 0 for option in options},
                'voters': {},  # Track who voted for what
                'closed': False,
                'author_id': ctx.author.id,
                'channel_id': ctx.channel.id,
                'message_id': poll_msg.id
            }
            
            await ctx.message.add_reaction('✅')  # Confirm poll creation
        except Exception as e:
            await ctx.send(f"❌ Error creating poll: {str(e)}")
            return

    @commands.command()
    async def closepoll(self, ctx, poll_msg_link=None):
        """Close a poll and display the results.
        
        Ends an active poll and shows the final vote counts for each option.
        You need to provide the poll message link or ID.
        
        Usage:
        !closepoll <poll_message_link>
        
        Example:
        !closepoll https://discord.com/channels/123456789012345678/123456789012345678/123456789012345678
        """
        # Check if poll message link is provided
        if poll_msg_link is None:
            await ctx.send("❌ Error: Please provide a link to the poll message.\nUsage: `!closepoll <poll_message_link>`")
            return
            
        # Extract message ID from link
        try:
            if poll_msg_link.isdigit():
                poll_msg_id = int(poll_msg_link)
            else:
                # Extract message ID from Discord message link
                match = re.search(r'/channels/\d+/\d+/(\d+)', poll_msg_link)
                if match:
                    poll_msg_id = int(match.group(1))
                else:
                    poll_msg_id = int(poll_msg_link.split('/')[-1])
        except (ValueError, IndexError):
            await ctx.send("❌ Error: Invalid poll message link. Please provide a valid Discord message link or ID.")
            return

        # Check if poll exists
        if poll_msg_id not in self.polls:
            await ctx.send("❌ Error: That message is not a valid poll.")
            return

        # Check if poll is already closed
        if self.polls[poll_msg_id]['closed']:
            await ctx.send("⚠️ The poll is already closed.")
            return

        poll_data = self.polls[poll_msg_id]
        if poll_data['author_id'] != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ Error: You can only close polls that you created, or you need the 'Manage Messages' permission.")
            return

        # Close the poll
        self.polls[poll_msg_id]['closed'] = True
        
        # Update the original poll message to show it's closed if possible
        try:
            channel = self.client.get_channel(poll_data['channel_id'])
            if channel:
                message = await channel.fetch_message(poll_msg_id)
                if message:
                    embed = message.embeds[0]
                    embed.title = f"📊 [CLOSED] {embed.title[2:]}"  # Add [CLOSED] to title
                    embed.color = discord.Color.red()
                    await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating poll message: {e}")
            
        await ctx.send("✅ The poll is now closed. Use `!results {poll_msg_id}` to view the results.")

    @commands.command()
    async def results(self, ctx, poll_msg_link=None):
        """View the results of a poll.
        
        Shows the current vote counts for each option in a poll.
        You need to provide the poll message link or ID.
        
        Usage:
        !results <poll_message_link>
        
        Example:
        !results https://discord.com/channels/123456789012345678/123456789012345678/123456789012345678
        """
        # Check if poll message link is provided
        if poll_msg_link is None:
            await ctx.send("❌ Error: Please provide a link to the poll message.\nUsage: `!results <poll_message_link>`")
            return
            
        # Extract message ID from link
        try:
            if poll_msg_link.isdigit():
                poll_msg_id = int(poll_msg_link)
            else:
                # Extract message ID from Discord message link
                match = re.search(r'/channels/\d+/\d+/(\d+)', poll_msg_link)
                if match:
                    poll_msg_id = int(match.group(1))
                else:
                    poll_msg_id = int(poll_msg_link.split('/')[-1])
        except (ValueError, IndexError):
            await ctx.send("❌ Error: Invalid poll message link. Please provide a valid Discord message link or ID.")
            return

        # Check if poll exists
        if poll_msg_id not in self.polls:
            await ctx.send("❌ Error: That message is not a valid poll.")
            return

        poll_data = self.polls[poll_msg_id]
        
        # Check if poll is closed
        if not poll_data['closed']:
            # Allow viewing results of open polls but with a warning
            await ctx.send("⚠️ Warning: The poll is still open. Results may change.\nUse `!closepoll {poll_msg_link}` to close it.")

        # Count votes from the voters dictionary
        self._count_votes(poll_msg_id)
        
        # Calculate total votes
        total_votes = sum(poll_data['votes'].values())
        
        # Create results embed
        embed = discord.Embed(
            title=f"📊 Poll Results: {poll_data['question']}", 
            description=f"Total votes: {total_votes}",
            color=discord.Color.green() if poll_data['closed'] else discord.Color.gold()
        )
        
        # Sort options by vote count (descending)
        sorted_options = sorted(poll_data['votes'].items(), key=lambda x: x[1], reverse=True)
        
        # Add options with vote counts and visual bars
        for option, votes in sorted_options:
            percentage = (votes / total_votes) * 100 if total_votes > 0 else 0
            bar_length = int(percentage / 5)  # 20 segments for 100%
            bar = '█' * bar_length + '░' * (20 - bar_length)
            embed.add_field(
                name=f"{option}",
                value=f"`{bar}` **{votes}** votes ({percentage:.1f}%)",
                inline=False
            )
        
        # Add footer with status
        status = "Closed" if poll_data['closed'] else "Still Open"
        embed.set_footer(text=f"Poll Status: {status} • Created by {ctx.guild.get_member(poll_data['author_id']).display_name if ctx.guild.get_member(poll_data['author_id']) else 'Unknown'}")
        
        await ctx.send(embed=embed)

    def _count_votes(self, poll_msg_id):
        """Count votes for a poll based on the voters dictionary"""
        poll_data = self.polls[poll_msg_id]
        
        # Reset vote counts
        poll_data['votes'] = {option: 0 for option in poll_data['options']}
        
        # Count votes from the voters dictionary
        for user_id, option_idx in poll_data['voters'].items():
            if 0 <= option_idx < len(poll_data['options']):
                poll_data['votes'][poll_data['options'][option_idx]] += 1
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user == self.client.user:
            return

        poll_msg_id = reaction.message.id
        if poll_msg_id not in self.polls:
            return

        poll_data = self.polls[poll_msg_id]
        if poll_data['closed']:
            # Remove reactions on closed polls
            try:
                await reaction.remove(user)
            except:
                pass
            return

        option_emojis = [chr(127462 + i) for i in range(1, len(poll_data['options']) + 1)]
        if reaction.emoji in option_emojis:
            option_idx = ord(reaction.emoji) - 127462 - 1  # Adjust index to be 0-based
            
            # Store the user's vote, overwriting any previous vote
            poll_data['voters'][user.id] = option_idx
            
            # Remove other reactions from this user on this poll
            try:
                for r in reaction.message.reactions:
                    if r.emoji != reaction.emoji and r.emoji in option_emojis:
                        users = await r.users().flatten()
                        if user in users:
                            await r.remove(user)
            except Exception as e:
                print(f"Error removing reactions: {e}")
    
    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        if user == self.client.user:
            return

        poll_msg_id = reaction.message.id
        if poll_msg_id not in self.polls:
            return

        poll_data = self.polls[poll_msg_id]
        if poll_data['closed']:
            return

        option_emojis = [chr(127462 + i) for i in range(1, len(poll_data['options']) + 1)]
        if reaction.emoji in option_emojis and user.id in poll_data['voters']:
            option_idx = ord(reaction.emoji) - 127462 - 1
            
            # If the user removed their reaction for their recorded vote, remove their vote
            if poll_data['voters'][user.id] == option_idx:
                del poll_data['voters'][user.id]
    
    @commands.command()
    async def pollhelp(self, ctx):
        """Show help for poll commands"""
        embed = discord.Embed(
            title="📊 Poll Commands Help",
            description="Here's how to use the polling system:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Creating a Poll",
            value='''`!poll "Question" "Option 1" "Option 2"
                    Create a new poll with up to 10 options.''',
            inline=False
        )

        embed.add_field(
            name="Closing a Poll",
            value="`!closepoll <poll_message_link>`\n" +
                  "Close a poll so no more votes can be cast.",
            inline=False
        )
        
        embed.add_field(
            name="Viewing Results",
            value="`!results <poll_message_link>`\n" +
                  "View the current results of a poll.",
            inline=False
        )
        
        embed.add_field(
            name="Tips",
            value="• You can only vote for one option\n" +
                  "• Only the poll creator or moderators can close polls\n" +
                  "• You can view results of open polls, but they may change",
            inline=False
        )
        
        await ctx.send(embed=embed)

