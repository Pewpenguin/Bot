import subprocess
import logging
import sys
import os

def check_ffmpeg():
    """Check if FFmpeg is installed and available in the system PATH."""
    logger = logging.getLogger('music')
    logger.info("Checking FFmpeg installation")
    
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE,
                               text=True,
                               check=False)
        
        if result.returncode == 0:
            version_info = result.stdout.split('\n')[0]
            logger.info(f"FFmpeg is installed: {version_info}")
            return True, version_info
        else:
            logger.error(f"FFmpeg check failed with return code {result.returncode}")
            logger.error(f"Error output: {result.stderr}")
            return False, result.stderr
    except FileNotFoundError:
        logger.error("FFmpeg not found in system PATH")
        return False, "FFmpeg not found in system PATH"
    except Exception as e:
        logger.error(f"Error checking FFmpeg: {str(e)}")
        return False, str(e)

def get_ffmpeg_path():
    """Get the path to FFmpeg executable."""
    logger = logging.getLogger('music')
    
    try:
        if sys.platform == 'win32':
            result = subprocess.run(['where', 'ffmpeg'], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True,
                                  check=False)
        else:
            result = subprocess.run(['which', 'ffmpeg'], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True,
                                  check=False)
            
        if result.returncode == 0:
            ffmpeg_path = result.stdout.strip()
            logger.info(f"FFmpeg path: {ffmpeg_path}")
            return ffmpeg_path
        else:
            logger.warning("Could not determine FFmpeg path")
            return None
    except Exception as e:
        logger.error(f"Error getting FFmpeg path: {str(e)}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, 
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('ffmpeg_check')
    
    is_installed, info = check_ffmpeg()
    if is_installed:
        print(f"FFmpeg is installed: {info}")
        path = get_ffmpeg_path()
        if path:
            print(f"FFmpeg path: {path}")
    else:
        print(f"FFmpeg is not properly installed: {info}")
        print("Please install FFmpeg and make sure it's in your system PATH.")