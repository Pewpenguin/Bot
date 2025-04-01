import discord
import asyncio
import yt_dlp
import re
import itertools
import logging
from discord.ext import commands
from async_timeout import timeout
from functools import partial

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

    __slots__ = ('bot', 'guild', 'channel', 'cog', 'queue', 'next', 'current', 'volume')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog
        
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        
        self.volume = 0.5
        self.current = None
        
        ctx.bot.loop.create_task(self.player_loop())

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
                embed.set_footer(text=f"Volume: {self.volume*100}%")
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
        return self.bot.loop.create_task(self.cog.cleanup(guild))


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
        """Connect to voice.
        Parameters
        ------------
        channel: discord.VoiceChannel [Optional]
            The channel to connect to. If a channel is not specified, an attempt to join the voice channel you are in
            will be made.
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
        """Request a song and add it to the queue.
        This command attempts to join a valid voice channel if the bot is not already in one.
        Uses YTDL to automatically search and retrieve a song.
        Parameters
        ------------
        search: str [Required]
            The song to search and retrieve using YTDL. This could be a simple search, an ID or URL.
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
                await player.queue.put(source)
                await ctx.send(f'**{source["title"]}** has been added to the queue.')
                logger.debug(f"Queue size after adding song: {player.queue.qsize()}")

    @commands.command(name='pause')
    async def pause_(self, ctx):
        """Pause the currently playing song."""
        vc = ctx.voice_client
        
        if not vc or not vc.is_playing():
            return await ctx.send('I am not currently playing anything!')
        elif vc.is_paused():
            return await ctx.send('I am already paused!')
        
        vc.pause()
        await ctx.send(f'**{ctx.author}**: Paused the song!')

    @commands.command(name='resume')
    async def resume_(self, ctx):
        """Resume the currently paused song."""
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!')
        elif not vc.is_paused():
            return await ctx.send('I am not currently paused!')
        
        vc.resume()
        await ctx.send(f'**{ctx.author}**: Resumed the song!')

    @commands.command(name='skip')
    async def skip_(self, ctx):
        """Skip the song."""
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently playing anything!')
        
        if vc.is_paused():
            pass
        elif not vc.is_playing():
            return await ctx.send('I am not currently playing anything!')
        
        vc.stop()
        await ctx.send(f'**{ctx.author}**: Skipped the song!')

    @commands.command(name='queue', aliases=['q', 'playlist'])
    async def queue_info(self, ctx):
        """Retrieve a basic queue of upcoming songs."""
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!')
        
        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send('There are currently no more queued songs.')
        
        # Grab up to 5 entries from the queue...
        upcoming = list(itertools.islice(player.queue._queue, 0, 5))
        
        fmt = '\n'.join(f'**`{_["title"]}`**' for _ in upcoming)
        embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}', description=fmt, color=discord.Color.green())
        
        await ctx.send(embed=embed)

    @commands.command(name='now_playing', aliases=['np', 'current', 'currentsong', 'playing'])
    async def now_playing_(self, ctx):
        """Display information about the currently playing song."""
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
    async def change_volume(self, ctx, *, volume: float):
        """Change the player volume.
        Parameters
        ------------
        volume: float or int [Required]
            The volume to set the player to in percentage. This must be between 1 and 100.
        """
        vc = ctx.voice_client
        
        if not vc or not vc.is_connected():
            return await ctx.send('I am not currently connected to voice!')
        
        if not 0 < volume < 101:
            return await ctx.send('Please enter a value between 1 and 100.')
        
        player = self.get_player(ctx)
        
        if vc.source:
            vc.source.volume = volume / 100
        
        player.volume = volume / 100
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
        
        await self.cleanup(ctx.guild)
        await ctx.send(f'**{ctx.author}**: Disconnected from voice channel.')