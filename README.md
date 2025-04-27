# Discord Bot with Music Player and Statistics

This Discord bot includes role management, moderation, polls, and a YouTube music player.

## Features

### Server Statistics
- Track member count changes over time
- Monitor message activity by channel, hour, and day
- Track command usage frequency
- Monitor voice channel activity
- View statistics with interactive commands

### Music Player
- Play music from YouTube
- Queue system for multiple songs
- Volume control
- Skip, pause, and resume functionality
- Display current song information

### Moderation
- Mute/unmute users
- Clear messages
- Temporary ban

### Role Management
- Reaction roles

### Polls
- Create polls with reactions

## Setup

### Prerequisites
- Python 3.8 or higher
- FFmpeg installed on your system
- Discord Bot Token
- MongoDB and Redis databases

### Installation

1. Clone this repository or download the source code:
```
git clone https://github.com/Pewpenguin/Bot
cd discord-bot
```

2. Create a virtual environment (recommended):
```
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

3. Install the required dependencies:
```
pip install -r requirements.txt
```

4. Install FFmpeg:

   **Windows:**
   - Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html)
   - Extract the files to a folder (e.g., `C:\ffmpeg`)
   - Add the bin folder to your PATH environment variable:
     - Right-click on 'This PC' > Properties > Advanced system settings > Environment Variables
     - Edit the PATH variable and add the path to the bin folder (e.g., `C:\ffmpeg\bin`)
   - Verify installation by running `ffmpeg -version` in a new command prompt

   **macOS:**
   - Using Homebrew: `brew install ffmpeg`
   - Verify installation: `ffmpeg -version`

   **Linux (Ubuntu/Debian):**
   - `sudo apt update && sudo apt install ffmpeg`
   - Verify installation: `ffmpeg -version`

5. Set up your Discord Bot:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application and add a bot to it
   - Enable necessary Intents (Server Members, Message Content, etc.)
   - Copy your bot token
   - Create a `config.py` file in the config directory with the following content:
     ```python
     BOT_TOKEN = 'your_bot_token_here'
     ```

6. Run the bot:
```
python main.py
```

## Music Commands

- `!join` - Join your voice channel
- `!play [song name or URL]` - Play a song from YouTube
- `!pause` - Pause the current song
- `!resume` - Resume the paused song
- `!skip` - Skip the current song
- `!queue` - Show the current queue (up to 5 songs)
- `!now_playing` - Show information about the current song
- `!volume [1-100]` - Change the volume
- `!stop` - Stop playing and clear the queue
- `!leave` - Disconnect from the voice channel

## Statistics Commands

- `!stats` - Shows a general overview of server statistics
- `!stats messages` - Displays detailed message statistics
- `!stats commands` - Shows command usage statistics
- `!stats members` - Displays member count statistics
- `!stats voice` - Shows voice channel usage statistics
- `!stats reset` - Resets all statistics (Admin only)

## Note

Make sure your Discord bot has the necessary permissions to join voice channels and send messages.