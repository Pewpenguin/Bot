import discord
from discord.ext import commands
import aiofiles

class Role(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.reaction_roles = []
        self.client.loop.create_task(self.load_reaction_roles())

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        for role_id, msg_id, emoji in self.reaction_roles:
            if msg_id == payload.message_id and emoji == str(payload.emoji.name.encode("utf-8")):
                try:
                    guild = self.client.get_guild(payload.guild_id)
                    if not guild:
                        return
                    
                    member = guild.get_member(payload.user_id)
                    if not member:
                        return
                    
                    role = guild.get_role(role_id)
                    if not role:
                        return
                        
                    await member.add_roles(role)
                except discord.Forbidden:
                    print(f"Error: Bot doesn't have permission to add role {role_id} to member {payload.user_id}")
                except Exception as e:
                    print(f"Error adding reaction role: {str(e)}")
                return

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        for role_id, msg_id, emoji in self.reaction_roles:
            if msg_id == payload.message_id and emoji == str(payload.emoji.name.encode("utf-8")):
                try:
                    guild = self.client.get_guild(payload.guild_id)
                    if not guild:
                        return
                    
                    member = guild.get_member(payload.user_id)
                    if not member:
                        return
                    
                    role = guild.get_role(role_id)
                    if not role:
                        return
                        
                    await member.remove_roles(role)
                except discord.Forbidden:
                    print(f"Error: Bot doesn't have permission to remove role {role_id} from member {payload.user_id}")
                except Exception as e:
                    print(f"Error removing reaction role: {str(e)}")
                return

    @commands.command()
    async def set_reaction(self, ctx, role: discord.Role = None, msg: discord.Message = None, emoji=None):
        """Create a reaction role for a message.
        
        Sets up a reaction role system where users can click on a reaction to get a role.
        The bot will add the specified emoji to the message and assign the role when users react.
        
        Usage:
        !set_reaction @role message_id emoji
        
        Parameters:
        - role: The role to assign (mention or ID)
        - msg: The message to add reactions to (message ID or link)
        - emoji: The emoji to use for the reaction
        
        Example:
        !set_reaction @Member 123456789012345678 👍
        """
        if role is None:
            await ctx.send("❌ Error: Please provide a valid role.")
            return
        if msg is None:
            await ctx.send("❌ Error: Please provide a valid message.")
            return
        if emoji is None:
            await ctx.send("❌ Error: Please provide a valid emoji.")
            return
            
        try:
            # Check if bot has permission to add reactions
            if not ctx.channel.permissions_for(ctx.guild.me).add_reactions:
                await ctx.send("❌ Error: I don't have permission to add reactions in this channel.")
                return
                
            await msg.add_reaction(emoji)
            self.reaction_roles.append((role.id, msg.id, str(emoji.encode("utf-8"))))

            try:
                async with aiofiles.open("reaction_roles.txt", mode="a") as file:
                    emoji_utf = emoji.encode("utf-8")
                    await file.write(f"{role.id} {msg.id} {emoji_utf}\n")
            except IOError as e:
                await ctx.send(f"⚠️ Warning: Reaction role was set but could not be saved to file: {str(e)}")
                return

            await ctx.send(f"✅ Success: Reaction role has been set! Users who react with {emoji} will receive the '{role.name}' role.")            
        except discord.Forbidden:
            await ctx.send("❌ Error: I don't have permission to add reactions to that message.")
        except discord.NotFound:
            await ctx.send("❌ Error: The message or emoji could not be found.")
        except discord.InvalidArgument:
            await ctx.send("❌ Error: The emoji is invalid.")
        except Exception as e:
            await ctx.send(f"❌ Error: An unexpected error occurred: {str(e)}")
            print(f"Error in set_reaction: {str(e)}")

    @commands.command()
    async def assign_role(self, ctx, role: discord.Role = None, member: discord.Member = None):
        """Manually assign a role to a member.
        
        Gives a specified role to a member in the server.
        Requires appropriate permissions to manage roles.
        
        Usage:
        !assign_role @role @member
        
        Parameters:
        - role: The role to assign (mention or ID)
        - member: The member to receive the role (mention or ID)
        
        Example:
        !assign_role @Moderator @User
        """
        if role is None:
            await ctx.send("❌ Error: Please provide a valid role.")
            return
        if member is None:
            await ctx.send("❌ Error: Please provide a valid member.")
            return
            
        # Check if bot has permission to manage roles
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ Error: I don't have permission to manage roles in this server.")
            return
            
        # Check if bot's role is higher than the role to assign
        if ctx.guild.me.top_role <= role:
            await ctx.send("❌ Error: I can't assign a role that is higher than or equal to my highest role.")
            return

        try:
            await member.add_roles(role)
            await ctx.send(f"✅ Success: Role '{role.name}' has been assigned to {member.mention}.")
        except discord.Forbidden:
            await ctx.send("❌ Error: I don't have permission to assign that role.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: Failed to assign role: {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ Error: An unexpected error occurred: {str(e)}")
            print(f"Error in assign_role: {str(e)}")

    @commands.command()
    async def unassign_role(self, ctx, role: discord.Role = None, member: discord.Member = None):
        if role is None:
            await ctx.send("❌ Error: Please provide a valid role.")
            return
        if member is None:
            await ctx.send("❌ Error: Please provide a valid member.")
            return
            
        # Check if bot has permission to manage roles
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ Error: I don't have permission to manage roles in this server.")
            return
            
        # Check if bot's role is higher than the role to remove
        if ctx.guild.me.top_role <= role:
            await ctx.send("❌ Error: I can't remove a role that is higher than or equal to my highest role.")
            return
            
        # Check if member has the role
        if role not in member.roles:
            await ctx.send(f"⚠️ Warning: {member.mention} doesn't have the role '{role.name}'.")
            return

        try:
            await member.remove_roles(role)
            await ctx.send(f"✅ Success: Role '{role.name}' has been removed from {member.mention}.")
        except discord.Forbidden:
            await ctx.send("❌ Error: I don't have permission to remove that role.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: Failed to remove role: {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ Error: An unexpected error occurred: {str(e)}")
            print(f"Error in unassign_role: {str(e)}")

    @commands.command()
    async def create_role(self, ctx, role_name=None, color=None):
        # Check if role name is provided
        if role_name is None:
            await ctx.send("❌ Error: Please provide a name for the role.")
            return
            
        # Check if bot has permission to manage roles
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ Error: I don't have permission to create roles in this server.")
            return
            
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
        color_message = ""
        
        if color is not None:
            color = color.lower()
            # Check if it's a named color
            if color in color_names:
                role_color = discord.Color(color_names[color])
                color_message = f" with {color} color"
            # Check if it's a hex color code (with or without #)
            elif color.startswith('#') and len(color) == 7:
                try:
                    role_color = discord.Color(int(color[1:], 16))
                    color_message = f" with custom color {color}"
                except ValueError:
                    await ctx.send(f"⚠️ Warning: Invalid hex color format '{color}'. Using default color instead.")
                    await ctx.send("Hex colors should be in format #RRGGBB where each letter is a hexadecimal digit (0-9, A-F).")
            elif len(color) == 6:
                try:
                    role_color = discord.Color(int(color, 16))
                    color_message = f" with custom color #{color}"
                except ValueError:
                    await ctx.send(f"⚠️ Warning: Invalid hex color format '{color}'. Using default color instead.")
                    await ctx.send("Hex colors should be in format RRGGBB where each letter is a hexadecimal digit (0-9, A-F).")
            else:
                await ctx.send(f"⚠️ Warning: Unknown color '{color}'. Using default color instead.")
                await ctx.send("Available colors: " + ", ".join(color_names.keys()) + " or use hex code like #FF0000")

        try:
            role = await ctx.guild.create_role(name=role_name, color=role_color)
            await ctx.send(f"✅ Success: Role '{role.name}' has been created{color_message}.")
        except discord.Forbidden:
            await ctx.send("❌ Error: I don't have the necessary permissions to create roles.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: Failed to create role: {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ Error: An unexpected error occurred: {str(e)}")
            print(f"Error in create_role: {str(e)}")

    @commands.command()
    async def delete_role(self, ctx, role: discord.Role = None):
        if role is None:
            await ctx.send("❌ Error: Please provide a valid role to delete.")
            return
            
        # Check if bot has permission to manage roles
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ Error: I don't have permission to delete roles in this server.")
            return
            
        # Check if bot's role is higher than the role to delete
        if ctx.guild.me.top_role <= role:
            await ctx.send("❌ Error: I can't delete a role that is higher than or equal to my highest role.")
            return

        try:
            role_name = role.name  # Store name before deletion
            await role.delete()
            await ctx.send(f"✅ Success: Role '{role_name}' has been deleted.")
        except discord.Forbidden:
            await ctx.send("❌ Error: I don't have the necessary permissions to delete roles.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: Failed to delete role: {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ Error: An unexpected error occurred: {str(e)}")
            print(f"Error in delete_role: {str(e)}")

    @commands.command()
    async def role_info(self, ctx, role: discord.Role = None):
        if role is None:
            await ctx.send("❌ Error: Please provide a valid role to get information.")
            return

        try:
            embed = discord.Embed(title=f"Role Information: {role.name}", color=role.color)
            embed.add_field(name="Role ID", value=role.id, inline=False)
            embed.add_field(name="Role Position", value=role.position, inline=False)
            embed.add_field(name="Members with this Role", value=len(role.members), inline=False)
            
            # Format permissions with emoji indicators
            if role.permissions.value > 0:
                permissions = "\n".join(f"✓ {permission.replace('_', ' ').title()}" 
                                      for permission, value in role.permissions if value)
            else:
                permissions = "No special permissions"
                
            embed.add_field(name="Role Permissions", value=permissions, inline=False)
            embed.set_footer(text=f"Created at: {role.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Error: Failed to retrieve role information: {str(e)}")
            print(f"Error in role_info: {str(e)}")

    async def load_reaction_roles(self):
        try:
            self.reaction_roles = []
            async with aiofiles.open("reaction_roles.txt", mode="r") as file:
                async for line in file:
                    try:
                        line = line.strip()
                        if line:
                            parts = line.split(" ", 2)
                            if len(parts) == 3:
                                role_id = int(parts[0])
                                msg_id = int(parts[1])
                                emoji = parts[2]
                                self.reaction_roles.append((role_id, msg_id, emoji))
                    except Exception as e:
                        print(f"Error parsing reaction role line: {str(e)}")
            print(f"Loaded {len(self.reaction_roles)} reaction roles")
        except FileNotFoundError:
            # File doesn't exist yet, which is fine for first run
            pass
        except Exception as e:
            print(f"Error loading reaction roles: {str(e)}")

    @commands.command()
    async def change_permissions(self, ctx, role: discord.Role = None, **perms):
        if role is None:
            await ctx.send("❌ Error: Please provide a valid role to change permissions.")
            return
            
        if not perms:
            await ctx.send("❌ Error: Please provide at least one permission to change.")
            await ctx.send("Example: !change_permissions @Role send_messages=True read_messages=False")
            return
            
        # Check if bot has permission to manage roles
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.send("❌ Error: I don't have permission to edit roles in this server.")
            return
            
        # Check if bot's role is higher than the role to edit
        if ctx.guild.me.top_role <= role:
            await ctx.send("❌ Error: I can't edit a role that is higher than or equal to my highest role.")
            return

        try:
            await role.edit(**perms)
            
            # Create a readable list of the changes made
            changes = [f"{perm.replace('_', ' ').title()}: {value}" for perm, value in perms.items()]
            changes_text = "\n".join(changes)
            
            embed = discord.Embed(
                title="Role Permissions Updated",
                description=f"Role: {role.mention}",
                color=role.color
            )
            embed.add_field(name="Changes Made", value=changes_text)
            
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Error: I don't have the necessary permissions to edit roles.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Error: Failed to update permissions: {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ Error: An unexpected error occurred: {str(e)}")
            print(f"Error in change_permissions: {str(e)}")