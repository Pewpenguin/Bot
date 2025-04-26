import discord
import asyncio
import yt_dlp
import re
import itertools
import logging
import json
from discord.ext import commands
from async_timeout import timeout
from functools import partial
from utils.database import db

logger = logging.getLogger('music')

yt_dlp.utils.bug_reports_message = lambda: ''

# YouTube URL patterns
YTDL_REGEX = re.compile(r'^((?:https?:)?//)?((?:www|m)\.)?((?:youtube\.com|youtu.be))(/(?:[\w\-]+\?v=|embed/|v/)?)([\w\-]+)(\S+)?$')

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader', 'Unknown')
        self.requester = None

    @classmethod
    async def create_source(cls, search: str, *, loop, requester=None):
        logger.info(f"Attempting to create source for search: {search}")
        loop = loop or asyncio.get_event_loop()
        
        try:
            logger.debug(f"Extracting info from URL: {search}")
            to_run = partial(cls.ytdl.extract_info, url=search, download=False)
            data = await loop.run_in_executor(None, to_run)
            
            if 'entries' in data:
                logger.debug(f"Playlist detected, taking first item")
                data = data['entries'][0]
                
            logger.debug(f"Successfully extracted data for: {data.get('title')}")
            source = {
                'url': data['url'],
                'title': data['title'],
                'duration': data.get('duration'),
                'thumbnail': data.get('thumbnail'),
                'requester': requester,
                'uploader': data.get('uploader', 'Unknown')
            }
            
            logger.info(f"Source created successfully for: {data.get('title')}")
            return source
        except Exception as e:
            logger.error(f"Error creating source: {str(e)}", exc_info=True)
            raise e
    
    @classmethod
    async def regather_stream(cls, data, *, loop):
        """Used for preparing a stream, instead of downloading."""
        logger.info(f"Regathering stream for: {data.get('title')}, URL: {data.get('url')}")
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']
        original_title = data.get('title')
        original_thumbnail = data.get('thumbnail') 
        original_uploader = data.get('uploader', 'Unknown')  
        original_duration = data.get('duration') 
        
        try:
            logger.debug(f"Extracting info for stream URL: {data['url']}")
            to_run = partial(cls.ytdl.extract_info, url=data['url'], download=False)
            extracted_data = await loop.run_in_executor(None, to_run)
            
            extracted_data['title'] = original_title
            extracted_data['thumbnail'] = extracted_data.get('thumbnail') or original_thumbnail
            extracted_data['uploader'] = extracted_data.get('uploader') or original_uploader
            extracted_data['duration'] = extracted_data.get('duration') or original_duration
            
            logger.debug(f"Creating FFmpegPCMAudio with URL: {extracted_data['url']}")
            source = cls(discord.FFmpegPCMAudio(extracted_data['url'], **FFMPEG_OPTIONS), data=extracted_data)
            source.requester = requester
            
           
            source.title = original_title  
            source.thumbnail = extracted_data['thumbnail']
            source.uploader = extracted_data['uploader']
            source.duration = extracted_data['duration']
            
            logger.info(f"Stream successfully regathered for: {original_title}")
            logger.debug(f"Title: {source.title}, Thumbnail URL: {source.thumbnail}, Uploader: {source.uploader}, Duration: {source.duration}")
            return source
        except Exception as e:
            logger.error(f"Error regathering stream: {str(e)}", exc_info=True)
            raise e


class MusicPlayer:
    """A class which is assigned to each guild using the bot for music.
    This class implements a queue and loop, which allows for different guilds to listen to different playlists
    simultaneously.
    When the bot disconnects from the Voice it's instance will be destroyed.
    """

    __slots__ = ('bot', 'guild', 'channel', 'cog', 'queue', 'next', 'current', 'volume', 'repeat_mode')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog
        
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        
        self.volume = 0.5
        self.current = None
        self.repeat_mode = "off"  # off, single, queue
        
        ctx.bot.loop.create_task(self.player_loop())
        ctx.bot.loop.create_task(self._load_settings())
        ctx.bot.loop.create_task(self._load_queue())

    async def _load_settings(self):
        """Load music settings from the database"""
        try:
            settings = await db.get_music_settings(str(self.guild.id))
            self.volume = settings.get("volume", 0.5)
            self.repeat_mode = settings.get("repeat_mode", "off")
            logger.info(f"Loaded music settings for guild: {self.guild.id}")
        except Exception as e:
            logger.error(f"Error loading music settings: {str(e)}", exc_info=True)
    
    async def _load_queue(self):
        """Load the music queue from Redis"""
        try:
            queue_data = await db.get_music_queue(str(self.guild.id))
            for track in queue_data:
                await self.queue.put(track)
            logger.info(f"Loaded {len(queue_data)} tracks from queue for guild: {self.guild.id}")
            
            # Also try to load current track
            current_track = await db.get_current_track(str(self.guild.id))
            if current_track:
                logger.info(f"Loaded current track: {current_track.get('title')} for guild: {self.guild.id}")
        except Exception as e:
            logger.error(f"Error loading music queue: {str(e)}", exc_info=True)
    
    async def _save_to_queue(self, track):
        """Save a track to the Redis queue"""
        try:
            await db.add_to_music_queue(str(self.guild.id), track)
            logger.debug(f"Saved track to queue: {track.get('title')}")
        except Exception as e:
            logger.error(f"Error saving track to queue: {str(e)}", exc_info=True)
    
    async def player_loop(self):
        """Our main player loop."""
        logger.info(f"Starting player loop for guild: {self.guild.id}")
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            self.next.clear()
            logger.debug(f"Waiting for the next song in queue for guild: {self.guild.id}")
            
            # Wait for the next song. If we timeout, cancel the player and disconnect
            try:
                async with timeout(300):  # 5 minutes
                    source = await self.queue.get()
                    logger.info(f"Got song from queue: {source.get('title')} for guild: {self.guild.id}")
            except asyncio.TimeoutError:
                logger.info(f"Player timed out after 5 minutes of inactivity for guild: {self.guild.id}")
                return self.destroy(self.guild)
            
            try:
                # Create a discord.FFmpegPCMAudio with the source
                logger.debug(f"Regathering stream for: {source.get('title')}")
                source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                source.volume = self.volume
                self.current = source
                
                # Save current track to Redis
                current_data = {
                    'url': source.url,
                    'title': source.title,
                    'duration': source.duration,
                    'thumbnail': source.thumbnail,
                    'requester_id': source.requester.id,
                    'requester_name': source.requester.display_name,
                    'uploader': source.uploader
                }
                await db.set_current_track(str(self.guild.id), current_data)
                
                if not self.guild.voice_client or not self.guild.voice_client.is_connected():
                    logger.error(f"Voice client disconnected before playback could start for guild: {self.guild.id}")
                    continue
                
                logger.info(f"Starting playback of: {source.title} in guild: {self.guild.id}")
                self.guild.voice_client.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self._after_playback, e))
                
                embed = discord.Embed(title="Now playing", description=f"[{source.title}]({source.url})", color=discord.Color.green())
                embed.set_thumbnail(url=source.thumbnail)
                embed.add_field(name="Duration", value=self.parse_duration(source.duration))
                embed.add_field(name="Requested by", value=source.requester.mention)
                embed.add_field(name="Uploader", value=source.uploader)
                embed.set_footer(text=f"Volume: {self.volume*100}% | Repeat: {self.repeat_mode}")
                await self.channel.send(embed=embed)
                
                logger.debug(f"Waiting for song to finish: {source.title} in guild: {self.guild.id}")
                await self.next.wait()
            except Exception as e:
                logger.error(f"Error during playback: {str(e)}", exc_info=True)
                await self.channel.send(f"An error occurred during playback: {str(e)}")
                self.next.set()
                continue
            finally:
                if source:
                    logger.debug(f"Cleaning up FFmpeg process for: {source.title}")
                    source.cleanup()
                
                # Handle repeat modes
                if self.repeat_mode == "single" and self.current:
                    # Put the current song back in the queue
                    current_data = {
                        'url': source.url,
                        'title': source.title,
                        'duration': source.duration,
                        'thumbnail': source.thumbnail,
                        'requester': source.requester,
                        'uploader': source.uploader
                    }
                    await self.queue.put(current_data)
                    await self._save_to_queue(current_data)
                elif self.repeat_mode == "queue" and self.queue.empty():
                    # If queue is empty and repeat mode is queue, reload all tracks
                    logger.info(f"Queue repeat mode: reloading all tracks for guild: {self.guild.id}")
                    try:
                        # Get all tracks from Redis
                        queue_data = await db.get_music_queue(str(self.guild.id))
                        if not queue_data and self.current:
                            # If Redis queue is empty but we have a current track, add it back
                            current_data = {
                                'url': source.url,
                                'title': source.title,
                                'duration': source.duration,
                                'thumbnail': source.thumbnail,
                                'requester': source.requester,
                                'uploader': source.uploader
                            }
                            await self.queue.put(current_data)
                            await self._save_to_queue(current_data)
                        else:
                            # Add all tracks back to the queue
                            for track in queue_data:
                                # Make sure requester is an object, not just an ID
                                if isinstance(track.get('requester'), dict) and 'id' in track['requester']:
                                    # Try to get the member object
                                    member = self.guild.get_member(int(track['requester']['id']))
                                    if member:
                                        track['requester'] = member
                                
                                await self.queue.put(track)
                                # No need to save to Redis as they're already there
                    except Exception as e:
                        logger.error(f"Error reloading queue in repeat mode: {str(e)}", exc_info=True)
                
                # Only clear current track from Redis if not in repeat mode
                if self.repeat_mode != "single":
                    await db.clear_current_track(str(self.guild.id))
                self.current = None
                logger.debug(f"Playback finished for guild: {self.guild.id}")
    
    def _after_playback(self, error):
        """Callback for when a song finishes playing."""
        if error:
            logger.error(f"Error after playback: {str(error)}")
        self.bot.loop.call_soon_threadsafe(self.next.set)
    
    @staticmethod
    def parse_duration(duration):
        if duration is None:
            return "Unknown"
        
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        
        duration_str = ""
        if hours > 0:
            duration_str += f"{hours}:"
        
        duration_str += f"{minutes:02d}:{seconds:02d}"
        return duration_str

    def destroy(self, guild):
        """Disconnect and cleanup the player."""
        # Save settings before destroying
        self.bot.loop.create_task(self._save_settings())
        return self.bot.loop.create_task(self.cog.cleanup(guild))
        
    async def _save_settings(self):
        """Save music settings to the database"""
        try:
            settings = {
                "volume": self.volume,
                "repeat_mode": self.repeat_mode
            }
            await db.update_music_settings(str(self.guild.id), settings)
            logger.info(f"Saved music settings for guild: {self.guild.id}")
        except Exception as e:
            logger.error(f"Error saving music settings: {str(e)}", exc_info=True)


class Music(commands.Cog):
    """Music related commands."""

    __slots__ = ('bot', 'players')

    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        logger.info("Initializing Music cog and setting up yt-dlp")
        try:
            self.ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
            logger.debug(f"yt-dlp initialized with options: {YTDL_OPTIONS}")
            YTDLSource.ytdl = self.ytdl
            logger.info("Music cog initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing yt-dlp: {str(e)}", exc_info=True)

    async def cleanup(self, guild):
        logger.info(f"Cleaning up player for guild: {guild.id}")
        try:
            # Save current queue to Redis before disconnecting
            if guild.id in self.players:
                player = self.players[guild.id]
                if player.current:
                    await db.clear_current_track(str(guild.id))
            
            await guild.voice_client.disconnect()
            logger.debug(f"Voice client disconnected for guild: {guild.id}")
        except AttributeError:
            logger.debug(f"No voice client to disconnect for guild: {guild.id}")
            pass
        
        try:  
            del self.players[guild.id]
            logger.debug(f"Player deleted for guild: {guild.id}")
        except KeyError:
            logger.debug(f"No player to delete for guild: {guild.id}")
            pass

    def get_player(self, ctx):
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player
        
        return player

    @commands.command(name='join', aliases=['connect'])
    async def connect_(self, ctx, *, channel: discord.VoiceChannel=None):
        """Connect to a voice channel.
        
        Makes the bot join a voice channel to play music.
        If no channel is specified, the bot will join your current voice channel.
        
        Usage:
        !join
        !join <channel>
        
        Parameters:
        - channel: The voice channel to join (optional)
        
        Examples:
        !join
        !join General Voice
        """
        logger.info(f"Connect command invoked by {ctx.author}")
        if not channel:
            try:
                channel = ctx.author.voice.channel
                logger.debug(f"Using author's voice channel: {channel.id}")
            except AttributeError:
                logger.warning(f"User {ctx.author} is not in a voice channel and did not specify one")
                await ctx.send('No channel to join. Please either specify a valid channel or join one.')
                return
        
        vc = ctx.voice_client
        logger.debug(f"Current voice client status: {vc is not None}")
        
        if vc:
            if vc.channel.id == channel.id:
                logger.debug(f"Already connected to channel: {channel.id}")
                return
            try:
                logger.info(f"Moving from channel {vc.channel.id} to {channel.id}")
                await vc.move_to(channel)
            except asyncio.TimeoutError:
                logger.error(f"Timeout while moving to channel: {channel.id}")
                await ctx.send(f'Moving to channel: <{channel}> timed out.')
                return
            except Exception as e:
                logger.error(f"Error moving to channel: {str(e)}", exc_info=True)
                await ctx.send(f'An error occurred while moving to the channel: {str(e)}')
                return
        else:
            try:
                logger.info(f"Connecting to channel: {channel.id}")
                await channel.connect()
            except asyncio.TimeoutError:
                logger.error(f"Timeout while connecting to channel: {channel.id}")
                await ctx.send(f'Connecting to channel: <{channel}> timed out.')
                return
            except Exception as e:
                logger.error(f"Error connecting to channel: {str(e)}", exc_info=True)
                await ctx.send(f'An error occurred while connecting to the channel: {str(e)}')
                return
        
        logger.info(f"Successfully connected to channel: {channel.id}")
        await ctx.send(f'Connected to: **{channel}**')

    @commands.command(name='play', aliases=['p'])
    async def play_(self, ctx, *, search: str):
        """Play a song or add it to the queue.
        
        Searches for and plays the requested song from YouTube.
        If a song is already playing, the requested song will be added to the queue.
        The bot will automatically join your voice channel if it isn't already connected.
        
        Usage:
        !play <search terms or URL>
        
        Parameters:
        - search: The song to play (YouTube URL or search terms)
        
        Examples:
        !play https://www.youtube.com/watch?v=dQw4w9WgXcQ
        !play never gonna give you up
        """
        logger.info(f"Play command invoked by {ctx.author} with search: {search}")
        async with ctx.channel.typing():
            vc = ctx.voice_client
            
            if not vc:
                logger.info(f"No voice client found, attempting to connect")
                await ctx.invoke(self.connect_)
                vc = ctx.voice_client
                if not vc:
                    logger.error(f"Failed to connect to voice channel")
                    await ctx.send("Failed to connect to voice channel. Please try again.")
                    return
            
            # Log voice client status
            logger.debug(f"Voice client status - Connected: {vc.is_connected()}, Playing: {vc.is_playing() if vc else False}")
            
            player = self.get_player(ctx)

            try:
                logger.info(f"Attempting to create source for: {search}")
                source = await YTDLSource.create_source(search, loop=self.bot.loop, requester=ctx.author)
                logger.debug(f"Source created successfully: {source['title']}")
            except Exception as e:
                logger.error(f"Error creating source: {str(e)}", exc_info=True)
                await ctx.send(f'An error occurred while processing this request: {str(e)}')
            else:
                logger.info(f"Adding {source['title']} to the queue")
                # Add to memory queue
                await player.queue.put(source)
                # Save to Redis queue
                await player._save_to_queue(source)
                await ctx.send(f'**{source["title"]}** has been added to the queue.')
                logger.debug(f"Queue size after adding song: {player.queue.qsize()}")

    @commands.command(name='pause')
    async def pause_(self, ctx):
        """Pause the currently playing song.
        
        Temporarily stops the audio playback. Use !resume to continue playing.
        
        Usage:
        !pause
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_playing():
            return await ctx.send('I am not currently playing anything!')
        elif vc.is_paused():
            return await ctx.send('I am already paused!')
        
        vc.pause()
        await ctx.send(f'**{ctx.author}**: Paused the song!')

    @commands.command(name='resume')
    async def resume_(self, ctx):
        """Resume the currently paused song.
        
        Continues playing a paused song from where it was stopped.
        
        Usage:
        !resume
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!')
        elif not vc.is_paused():
            return await ctx.send('I am not currently paused!')
        
        vc.resume()
        await ctx.send(f'**{ctx.author}**: Resumed the song!')

    @commands.command(name='skip')
    async def skip_(self, ctx):
        """Skip the currently playing song.
        
        Skips the current song and moves to the next song in the queue.
        If there are no more songs in the queue, the bot will stop playing.
        
        Usage:
        !skip
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!')
        
        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return await ctx.send('I am not currently playing anything!')
        
        vc.stop()
        await ctx.send(f'**{ctx.author}**: Skipped the song!')

    @commands.command(name='queue', aliases=['q'])
    async def queue_info(self, ctx):
        """Display the current music queue.
        
        Shows a list of all songs currently in the queue with their titles and requesters.
        Displays the currently playing song at the top of the list.
        
        Usage:
        !queue
        
        Aliases:
        !q
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!')
        
        # Get queue from Redis to ensure it's up to date
        queue_data = await db.get_music_queue(str(ctx.guild.id))
        
        if not queue_data:
            return await ctx.send('There are currently no more queued songs.')
        
        # Get current track
        current = await db.get_current_track(str(ctx.guild.id))
        
        # Create embed
        embed = discord.Embed(title="Music Queue", color=discord.Color.green())
        
        # Add current track
        if current:
            embed.add_field(
                name="Currently Playing:", 
                value=f"[{current['title']}]({current.get('url', 'https://youtube.com')})", 
                inline=False
            )
        
        # Add queue tracks (up to 10)
        queue_list = []
        for i, track in enumerate(queue_data[:10]):
            queue_list.append(f"`{i+1}.` {track['title']}")
        
        if queue_list:
            embed.add_field(
                name=f"Upcoming - Next {len(queue_list)}", 
                value="\n".join(queue_list), 
                inline=False
            )
            
            if len(queue_data) > 10:
                embed.set_footer(text=f"And {len(queue_data) - 10} more songs in queue")
        
        await ctx.send(embed=embed)

    @commands.command(name='now_playing', aliases=['np', 'current', 'currentsong', 'playing'])
    async def now_playing_(self, ctx):
        """Display information about the currently playing song.
        
        Shows details about the current song including title, duration, requester, and more.
        
        Usage:
        !now_playing
        !np (alias)
        !current (alias)
        !currentsong (alias)
        !playing (alias)
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!')
        
        player = self.get_player(ctx)
        if not player.current:
            return await ctx.send('I am not currently playing anything!')
        
        embed = discord.Embed(title="Now playing", description=f"[{player.current.title}]({player.current.url})", color=discord.Color.green())
        embed.set_thumbnail(url=player.current.thumbnail)
        embed.add_field(name="Duration", value=player.parse_duration(player.current.duration))
        embed.add_field(name="Requested by", value=player.current.requester.mention)
        embed.add_field(name="Uploader", value=player.current.uploader)
        embed.set_footer(text=f"Volume: {player.volume*100}%")
        
        await ctx.send(embed=embed)

    @commands.command(name='volume', aliases=['vol'])
    async def change_volume(self, ctx, *, volume: float=None):
        """Change or display the music volume.
        
        Adjusts the volume of the currently playing music.
        If no volume is specified, displays the current volume level.
        
        Usage:
        !volume [level]
        
        Parameters:
        - level: Volume level between 0 and 100 (optional)
        
        Examples:
        !volume 50 - Set volume to 50%
        !volume - Display current volume
        
        Aliases:
        !vol
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!')
        
        player = self.get_player(ctx)
        
        # If no volume specified, display current volume
        if volume is None:
            return await ctx.send(f'Current volume: **{int(player.volume * 100)}%**')
        
        if not 0 < volume < 101:
            return await ctx.send('Please enter a value between 1 and 100.')
        
        if vc.source:
            vc.source.volume = volume / 100
        
        player.volume = volume / 100
        
        # Save volume setting to database
        await db.update_music_settings(str(ctx.guild.id), {"volume": player.volume})
        
        await ctx.send(f'**{ctx.author}**: Set the volume to **{volume}%**')

    @commands.command(name='stop')
    async def stop_(self, ctx):
        """Stop the currently playing song and destroy the player.
        !Warning!
            This will destroy the player assigned to your guild, also deleting any queued songs and settings.
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!')
        
        # Clear the queue in Redis
        await db.clear_music_queue(str(ctx.guild.id))
        await db.clear_current_track(str(ctx.guild.id))
        
        await self.cleanup(ctx.guild)
        await ctx.send(f'**{ctx.author}**: Stopped the music!')

    @commands.command(name='leave', aliases=['disconnect'])
    async def leave_(self, ctx):
        """Stop the currently playing song and leave the voice channel.
        !Warning!
            This will destroy the player assigned to your guild, also deleting any queued songs and settings.
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!')
        
        # Clear the queue in Redis
        await db.clear_music_queue(str(ctx.guild.id))
        await db.clear_current_track(str(ctx.guild.id))
        
        await self.cleanup(ctx.guild)
        await ctx.send(f'**{ctx.author}**: Disconnected from voice channel.')
        
    @commands.command(name='repeat', aliases=['loop'])
    async def repeat_(self, ctx, mode: str = None):
        """Set the repeat mode for the music player.
        
        Changes how songs are repeated after they finish playing.
        
        Usage:
        !repeat [mode]
        
        Parameters:
        - mode: The repeat mode to set (off, single, queue)
        
        Examples:
        !repeat off - Turn off repeat
        !repeat single - Repeat the current song
        !repeat queue - Repeat the entire queue
        
        Aliases:
        !loop
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!')
        
        player = self.get_player(ctx)
        
        # If no mode specified, display current mode
        if mode is None:
            return await ctx.send(f'Current repeat mode: **{player.repeat_mode}**')
        
        # Validate mode
        mode = mode.lower()
        if mode not in ['off', 'single', 'queue']:
            return await ctx.send('Invalid repeat mode. Please use: off, single, or queue.')
        
        # Set mode
        player.repeat_mode = mode
        
        # Save to database
        await db.update_music_settings(str(ctx.guild.id), {"repeat_mode": mode})
        
        await ctx.send(f'**{ctx.author}**: Set repeat mode to **{mode}**')
    
    # Playlist commands
    @commands.group(name='playlist', aliases=['pl'], invoke_without_command=True)
    async def playlist_(self, ctx):
        """Manage your music playlists.
        
        Use subcommands to create, view, and manage your playlists.
        
        Usage:
        !playlist create <name> - Create a new playlist
        !playlist list - List your playlists
        !playlist view <name> - View songs in a playlist
        !playlist add <name> <song> - Add a song to a playlist
        !playlist remove <name> <index> - Remove a song from a playlist
        !playlist play <name> - Play a playlist
        !playlist delete <name> - Delete a playlist
        
        Aliases:
        !pl
        """
        await ctx.send_help(ctx.command)
    
    @playlist_.command(name='create')
    async def playlist_create(self, ctx, *, name: str):
        """Create a new playlist.
        
        Creates an empty playlist that you can add songs to later.
        
        Usage:
        !playlist create <name>
        
        Parameters:
        - name: The name for your new playlist
        
        Examples:
        !playlist create My Favorites
        """
        # Check if user already has a playlist with this name
        user_playlists = await db.get_playlists(str(ctx.author.id))
        for playlist in user_playlists:
            if playlist['name'].lower() == name.lower():
                return await ctx.send(f'You already have a playlist named **{name}**. Please choose a different name.')
        
        # Create the playlist
        playlist = await db.create_playlist(str(ctx.author.id), name)
        
        await ctx.send(f'Created new playlist: **{name}**')
    
    @playlist_.command(name='list')
    async def playlist_list(self, ctx):
        """List all your playlists.
        
        Shows all playlists you've created with their names and track counts.
        
        Usage:
        !playlist list
        """
        playlists = await db.get_playlists(str(ctx.author.id))
        
        if not playlists:
            return await ctx.send("You don't have any playlists yet. Create one with `!playlist create <name>`")
        
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Playlists", color=discord.Color.blue())
        
        for playlist in playlists:
            track_count = len(playlist.get('tracks', []))
            embed.add_field(
                name=playlist['name'],
                value=f"{track_count} tracks",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @playlist_.command(name='view')
    async def playlist_view(self, ctx, *, name: str):
        """View the songs in a playlist.
        
        Shows all songs in the specified playlist with their titles.
        
        Usage:
        !playlist view <name>
        
        Parameters:
        - name: The name of the playlist to view
        
        Examples:
        !playlist view My Favorites
        """
        # Find the playlist
        playlists = await db.get_playlists(str(ctx.author.id))
        playlist = None
        
        for p in playlists:
            if p['name'].lower() == name.lower():
                playlist = p
                break
        
        if not playlist:
            return await ctx.send(f"You don't have a playlist named **{name}**")
        
        tracks = playlist.get('tracks', [])
        
        if not tracks:
            return await ctx.send(f"Your playlist **{name}** is empty. Add songs with `!playlist add {name} <song>`")
        
        embed = discord.Embed(title=f"Playlist: {playlist['name']}", color=discord.Color.blue())
        
        # Add tracks (up to 15)
        track_list = []
        for i, track in enumerate(tracks[:15]):
            track_list.append(f"`{i+1}.` {track['title']}")
        
        embed.add_field(
            name=f"Tracks ({len(tracks)} total)", 
            value="\n".join(track_list), 
            inline=False
        )
        
        if len(tracks) > 15:
            embed.set_footer(text=f"And {len(tracks) - 15} more songs")
        
        await ctx.send(embed=embed)
    
    @playlist_.command(name='add')
    async def playlist_add(self, ctx, name: str, *, search: str):
        """Add a song to a playlist.
        
        Searches for a song and adds it to the specified playlist.
        
        Usage:
        !playlist add <name> <search>
        
        Parameters:
        - name: The name of the playlist to add to
        - search: The song to add (YouTube URL or search terms)
        
        Examples:
        !playlist add My Favorites never gonna give you up
        """
        # Find the playlist
        playlists = await db.get_playlists(str(ctx.author.id))
        playlist = None
        playlist_id = None
        
        for p in playlists:
            if p['name'].lower() == name.lower():
                playlist = p
                playlist_id = p['_id']
                break
        
        if not playlist:
            return await ctx.send(f"You don't have a playlist named **{name}**")
        
        # Search for the song
        async with ctx.channel.typing():
            try:
                source = await YTDLSource.create_source(search, loop=self.bot.loop, requester=ctx.author)
                
                # Add to playlist
                track_data = {
                    'url': source['url'],
                    'title': source['title'],
                    'duration': source.get('duration'),
                    'thumbnail': source.get('thumbnail'),
                    'uploader': source.get('uploader', 'Unknown'),
                    'added_at': datetime.datetime.utcnow().isoformat()
                }
                
                await db.add_track_to_playlist(playlist_id, track_data)
                
                await ctx.send(f"Added **{source['title']}** to playlist **{name}**")
                
            except Exception as e:
                logger.error(f"Error adding to playlist: {str(e)}", exc_info=True)
                await ctx.send(f'An error occurred while processing this request: {str(e)}')
    
    @playlist_.command(name='remove')
    async def playlist_remove(self, ctx, name: str, index: int):
        """Remove a song from a playlist.
        
        Removes the song at the specified index from the playlist.
        
        Usage:
        !playlist remove <name> <index>
        
        Parameters:
        - name: The name of the playlist to remove from
        - index: The index of the song to remove (starting from 1)
        
        Examples:
        !playlist remove My Favorites 3
        """
        # Find the playlist
        playlists = await db.get_playlists(str(ctx.author.id))
        playlist = None
        playlist_id = None
        
        for p in playlists:
            if p['name'].lower() == name.lower():
                playlist = p
                playlist_id = p['_id']
                break
        
        if not playlist:
            return await ctx.send(f"You don't have a playlist named **{name}**")
        
        # Adjust index (user input is 1-based, database is 0-based)
        db_index = index - 1
        
        # Check if index is valid
        if db_index < 0 or db_index >= len(playlist.get('tracks', [])):
            return await ctx.send(f"Invalid track index. The playlist has {len(playlist.get('tracks', []))} tracks.")
        
        # Get track title before removing
        track_title = playlist['tracks'][db_index]['title']
        
        # Remove from playlist
        result = await db.remove_track_from_playlist(playlist_id, db_index)
        
        if result:
            await ctx.send(f"Removed **{track_title}** from playlist **{name}**")
        else:
            await ctx.send(f"Failed to remove track from playlist. Please try again.")
    
    @playlist_.command(name='play')
    async def playlist_play(self, ctx, *, name: str):
        """Play a playlist.
        
        Adds all songs from the specified playlist to the queue.
        
        Usage:
        !playlist play <name>
        
        Parameters:
        - name: The name of the playlist to play
        
        Examples:
        !playlist play My Favorites
        """
        # Find the playlist
        playlists = await db.get_playlists(str(ctx.author.id))
        playlist = None
        
        for p in playlists:
            if p['name'].lower() == name.lower():
                playlist = p
                break
        
        if not playlist:
            return await ctx.send(f"You don't have a playlist named **{name}**")
        
        tracks = playlist.get('tracks', [])
        
        if not tracks:
            return await ctx.send(f"Your playlist **{name}** is empty. Add songs with `!playlist add {name} <song>`")
        
        # Connect to voice if not already connected
        vc = ctx.voice_client
        if not vc:
            await ctx.invoke(self.connect_)
            vc = ctx.voice_client
            if not vc:
                return await ctx.send("Failed to connect to voice channel. Please try again.")
        
        # Get player
        player = self.get_player(ctx)
        
        # Add tracks to queue
        added_count = 0
        async with ctx.channel.typing():
            for track in tracks:
                try:
                    # Create source object compatible with our player
                    source = {
                        'url': track['url'],
                        'title': track['title'],
                        'duration': track.get('duration'),
                        'thumbnail': track.get('thumbnail'),
                        'requester': ctx.author,
                        'uploader': track.get('uploader', 'Unknown')
                    }
                    
                    # Add to memory queue
                    await player.queue.put(source)
                    # Save to Redis queue
                    await player._save_to_queue(source)
                    added_count += 1
                    
                except Exception as e:
                    logger.error(f"Error adding track from playlist: {str(e)}", exc_info=True)
                    continue
        
        await ctx.send(f"Added **{added_count}** tracks from playlist **{name}** to the queue")
    
    @playlist_.command(name='delete')
    async def playlist_delete(self, ctx, *, name: str):
        """Delete a playlist.
        
        Permanently deletes the specified playlist.
        
        Usage:
        !playlist delete <name>
        
        Parameters:
        - name: The name of the playlist to delete
        
        Examples:
        !playlist delete My Favorites
        """
        # Find the playlist
        playlists = await db.get_playlists(str(ctx.author.id))
        playlist = None
        playlist_id = None
        
        for p in playlists:
            if p['name'].lower() == name.lower():
                playlist = p
                playlist_id = p['_id']
                break
        
        if not playlist:
            return await ctx.send(f"You don't have a playlist named **{name}**")
        
        # Delete the playlist
        await db.delete_playlist(playlist_id)
        
        await ctx.send(f"Deleted playlist **{name}**")