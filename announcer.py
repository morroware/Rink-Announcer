#!/usr/bin/env python3
"""
announcer.py

This module handles announcement operations including configuration loading,
speech synthesis, playing sounds, and fetching color data from the database.
It includes improved concurrency (global RLock and file locking with fcntl),
a retry mechanism for transient errors, and enhanced logging.
"""

import asyncio
import edge_tts
import pymssql
import datetime
import time
import sys
import os
import logging
import subprocess
import threading
import random
import functools
from typing import Optional, Dict, Tuple
from contextlib import contextmanager
import fcntl

# Global lock for shared resources and thread safety
global_lock = threading.RLock()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("announcement_script.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

# Global flag to signal configuration reload
config_reload_signal = False

class Config:
    def __init__(self):
        self.database = {
            "server": "",
            "database": "",
            "username": "",
            "password": ""
        }
        self.times = {}
        self.announcements = {
            "fiftyfive": "",
            "hour": "",
            "rules": "",
            "ad": ""
        }
        self.tts = {
            "voice_id": "",
            "output_format": "mp3"
        }

def get_day_config_filename() -> str:
    """
    Get the appropriate config filename based on the current day.
    Returns the default config.ini if not an operating day.
    """
    days_mapping = {
    0: "mon.ini",    # Monday
    1: "tue.ini",    # Tuesday
    2: "wed.ini",    # Wednesday
    3: "thurs.ini",  # Thursday
    4: "fri.ini",    # Friday
    5: "sat.ini",    # Saturday
    6: "sun.ini"     # Sunday
}

    current_day = datetime.datetime.now().weekday()
    return days_mapping.get(current_day, "config.ini")

def check_for_config_changes() -> bool:
    """
    Check if there's a request to reload the configuration.
    Checks both the reload_config file and the global reload signal.
    """
    global config_reload_signal
    if os.path.exists("reload_config"):
        logging.info("Found reload_config file – signaling configuration reload")
        return True
    if config_reload_signal:
        logging.info("Detected configuration reload signal")
        with global_lock:
            config_reload_signal = False
        return True
    return False

# File locking context manager using fcntl
@contextmanager
def locked_file(filepath, mode='r', lock_type=fcntl.LOCK_SH):
    with open(filepath, mode) as f:
        fcntl.flock(f, lock_type)
        try:
            yield f
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

# Retry decorator with exponential backoff
def retry(exceptions, tries=3, delay=1, backoff=2, jitter=0.1):
    def decorator_retry(func):
        @functools.wraps(func)
        def wrapper_retry(*args, **kwargs):
            _tries = tries
            _delay = delay
            while _tries > 1:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    logging.error(f"{func.__name__} error: {e}, retrying in {_delay} seconds")
                    time.sleep(_delay + random.uniform(0, jitter))
                    _tries -= 1
                    _delay *= backoff
            return func(*args, **kwargs)
        return wrapper_retry
    return decorator_retry

def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from the specified path or determine the appropriate day-based config.
    Uses file locking when accessing the reload_config and configuration files.
    """
    global config_reload_signal
    with global_lock:
        config_reload_signal = False

    try:
        if os.path.exists("reload_config"):
            with locked_file("reload_config", "r", fcntl.LOCK_SH) as f:
                requested_config = f.read().strip()
            if requested_config and os.path.exists(requested_config):
                config_path = requested_config
                logging.info(f"Loading requested configuration from reload_config: {config_path}")
            try:
                with locked_file("reload_config", "w", fcntl.LOCK_EX) as f:
                    pass
                os.remove("reload_config")
            except Exception as e:
                logging.warning(f"Could not remove reload_config file: {e}")

        if config_path is None:
            config_path = get_day_config_filename()

        config = Config()
        current_section = None

        if not os.path.exists(config_path):
            logging.error(f"Config file not found: {config_path}")
            if config_path != "config.ini":
                logging.warning("Falling back to default config.ini")
                config_path = "config.ini"
                if not os.path.exists(config_path):
                    raise FileNotFoundError(f"Default config file not found: {config_path}")
            else:
                raise FileNotFoundError(f"Config file not found: {config_path}")

        logging.info(f"Loading configuration from {config_path}")
        with locked_file(config_path, "r", fcntl.LOCK_SH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1].lower()
                    continue
                if '=' not in line:
                    continue
                key, value = [x.strip() for x in line.split('=', 1)]
                clean_value = value.strip('"\'')
                if current_section == 'database':
                    config.database[key.lower()] = clean_value
                elif current_section == 'times':
                    config.times[key] = clean_value
                elif current_section == 'announcements':
                    config.announcements[key.lower()] = clean_value
                elif current_section == 'tts':
                    if key.lower() == 'voice_id':
                        config.tts['voice_id'] = clean_value
                    elif key.lower() == 'output_format':
                        config.tts['output_format'] = clean_value.lower()

        if not all([config.database['server'], config.database['database'],
                    config.database['username'], config.database['password']]):
            raise ValueError("Missing required database configuration")
        if not config.tts['voice_id']:
            raise ValueError("Missing required TTS voice_id configuration")

        logging.info("Configuration loaded successfully")
        return config
    except Exception as e:
        logging.error(f"Error loading config: {e}", exc_info=True)
        raise

def calculate_next_1am() -> datetime.datetime:
    """
    Calculate the next 1:00 AM time.
    If current time is after 1 AM, returns 1 AM of the next day.
    """
    now = datetime.datetime.now()
    next_1am = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if now.hour >= 1:
        next_1am += datetime.timedelta(days=1)
    return next_1am

def schedule_config_reload(shutdown_event: threading.Event) -> None:
    """
    Schedule a daily configuration reload at 1:00 AM.
    """
    global config_reload_signal
    while not shutdown_event.is_set():
        now = datetime.datetime.now()
        next_1am = calculate_next_1am()
        seconds_until_1am = (next_1am - now).total_seconds()
        logging.info(f"Next configuration reload scheduled at {next_1am.strftime('%Y-%m-%d %H:%M:%S')} (in {int(seconds_until_1am)} seconds)")
        while seconds_until_1am > 0 and not shutdown_event.is_set():
            wait_time = min(60, seconds_until_1am)
            if shutdown_event.wait(timeout=wait_time):
                return
            seconds_until_1am -= wait_time
        if not shutdown_event.is_set():
            logging.info("It's 1:00 AM - signaling day-specific configuration reload")
            config_reload_signal = True

@retry(Exception, tries=3, delay=2, backoff=2)
def get_color_message_from_db(config: Config) -> Optional[Dict[str, Dict[str, str]]]:
    """
    Fetch color data from the database, rotating every 30 minutes.
    Retries automatically on transient errors.
    """
    try:
        logging.info(f"Connecting to database: {config.database['server']}")
        with pymssql.connect(
            server=config.database['server'],
            user=config.database['username'],
            password=config.database['password'],
            database=config.database['database'],
            timeout=30
        ) as conn:
            with conn.cursor() as cursor:
                query = """
                DECLARE @PrinterGroup INT = 1;
                DECLARE @CurrentTime TIME = CAST(CURRENT_TIMESTAMP AS TIME);
                DECLARE @ShiftStart TIME;
                SELECT @ShiftStart = shiftdatechangetime FROM applicationinfo;
                DECLARE @MinutesSinceStart INT = DATEDIFF(MINUTE, @ShiftStart, @CurrentTime);
                IF @MinutesSinceStart < 0
                    SET @MinutesSinceStart = @MinutesSinceStart + (24 * 60);
                DECLARE @CurrentInterval INT = (@MinutesSinceStart / 30) % (
                    SELECT COUNT(*) FROM ticketprintergroupcolors WHERE ticketprintergroupno = @PrinterGroup
                );
                DECLARE @TotalColors INT;
                SELECT @TotalColors = COUNT(*) FROM ticketprintergroupcolors WHERE ticketprintergroupno = @PrinterGroup;
                WITH ColorOrder AS (
                    SELECT
                        CASE color
                            WHEN -65536 THEN 'Red'
                            WHEN -256 THEN 'Yellow'
                            WHEN -16711681 THEN 'Blue'
                            WHEN -16711936 THEN 'Green'
                            WHEN -23296 THEN 'Orange'
                            ELSE 'Unknown'
                        END as color_name,
                        corder,
                        (ROW_NUMBER() OVER (ORDER BY corder) - 1 - @CurrentInterval + @TotalColors) % @TotalColors as adjusted_position
                    FROM ticketprintergroupcolors
                    WHERE ticketprintergroupno = @PrinterGroup
                )
                SELECT adjusted_position + 1 as position, color_name FROM ColorOrder ORDER BY position;
                """
                cursor.execute(query)
                rows = cursor.fetchall()
                if not rows:
                    logging.error("No colors found in database")
                    return None
                color_data = {}
                for row in rows:
                    position, color_name = row
                    color_data[f'color{position}'] = {
                        'color': str(color_name).strip(),
                        'time': f'Interval {position}'
                    }
                    logging.info(f"Position {position} -> Color: {color_name}")
                logging.info(f"Current color sequence: {color_data}")
                return color_data
    except Exception as e:
        logging.error(f"Database error in get_color_message_from_db: {e}", exc_info=True)
        raise

async def synthesize_speech_async(text: str, voice_id: str, output_path: str) -> bool:
    """
    Synthesize speech using edge_tts and save the result to a file.
    """
    try:
        logging.info(f"Synthesizing speech (first 50 chars): {text[:50]}...")
        communicate = edge_tts.Communicate(text, voice_id)
        await communicate.save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logging.info("Speech synthesis successful")
            return True
        else:
            logging.error("Speech synthesis failed – output file empty or missing")
            return False
    except Exception as e:
        logging.error(f"Error during speech synthesis: {e}", exc_info=True)
        return False

def play_sound(sound_path: str, output_format: str) -> bool:
    """
    Play a sound file using mpg123.
    """
    if not sound_path or not os.path.exists(sound_path):
        logging.error(f"Invalid sound path: {sound_path}")
        return False
    try:
        logging.info(f"Playing sound file: {sound_path}")
        if subprocess.run(['which', 'mpg123'], capture_output=True).returncode != 0:
            logging.error("mpg123 is not installed")
            return False
        subprocess.run(['mpg123', '-q', sound_path], check=True)
        logging.info("Sound played successfully")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error playing sound: {e}", exc_info=True)
        return False
    except Exception as e:
        logging.error(f"Error playing sound: {e}", exc_info=True)
        return False
    finally:
        try:
            os.remove(sound_path)
            logging.debug(f"Cleaned up sound file: {sound_path}")
        except Exception as e:
            logging.warning(f"Failed to clean up file {sound_path}: {e}")

def convert_to_12hr_format(time_str: str) -> str:
    """
    Convert a time string in 24-hour format (HH:MM) to 12-hour format with AM/PM.
    """
    try:
        hour, minute = map(int, time_str.split(':'))
        period = "PM" if hour >= 12 else "AM"
        if hour > 12:
            hour -= 12
        elif hour == 0:
            hour = 12
        return f"{hour}:{minute:02d} {period}"
    except Exception as e:
        logging.error(f"Error converting time format: {e}", exc_info=True)
        return time_str

def calculate_next_announcement(times: Dict[str, str], current_time: datetime.datetime) -> Optional[Tuple[datetime.datetime, str]]:
    """
    Calculate the next scheduled announcement.
    Returns a tuple (announcement_time, announcement_type) or None if no upcoming announcement exists.
    """
    announcement_times = []
    for time_str, announcement_type in times.items():
        try:
            hour, minute = map(int, time_str.split(':'))
            announcement_time = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if announcement_time <= current_time:
                # If the time has passed today, schedule it for tomorrow
                announcement_time += datetime.timedelta(days=1)
            announcement_times.append((announcement_time, announcement_type))
        except ValueError:
            logging.warning(f"Invalid time format in configuration: {time_str}")
            continue
    if not announcement_times:
        return None
    return min(announcement_times, key=lambda x: x[0])

def synthesize_announcement(template: str, announcement_type: str, time_str: str,
                            color_data: Dict[str, Dict[str, str]], config: Config) -> Optional[str]:
    """
    Generate and synthesize an announcement using a template and color data.
    Returns the path to the synthesized audio file or None on failure.
    """
    try:
        time_12hr = convert_to_12hr_format(time_str)
        logging.info(f"Generating announcement for type: {announcement_type}")

        if not color_data:
            logging.warning("No color data available; using default placeholders")
            color_data = {
                'color1': {'color': 'unknown'},
                'color2': {'color': 'unknown'},
                'color3': {'color': 'unknown'},
                'color4': {'color': 'unknown'}
            }

        format_vars = {
            'time': time_12hr,
            'color1': color_data.get('color1', {}).get('color', 'unknown'),
            'color2': color_data.get('color2', {}).get('color', 'unknown'),
            'color3': color_data.get('color3', {}).get('color', 'unknown'),
            'color4': color_data.get('color4', {}).get('color', 'unknown')
        }

        logging.info(f"Template before formatting: {template}")
        logging.info(f"Format variables: {format_vars}")

        try:
            announcement_text = template.format(**format_vars)
            logging.info(f"Announcement text generated: {announcement_text}")
        except KeyError as e:
            logging.error(f"Template formatting error – missing key: {e}")
            return None
        except Exception as e:
            logging.error(f"Template formatting error: {e}")
            return None

        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_path = temp_file.name

        success = asyncio.run(synthesize_speech_async(announcement_text, config.tts['voice_id'], temp_path))
        if success:
            return temp_path
        else:
            return None
    except Exception as e:
        logging.error(f"Error synthesizing announcement: {e}", exc_info=True)
        return None

def main():
    """
    Main function for the announcer.
    Sets up configuration reload scheduling and handles the announcement loop.
    """
    shutdown_event = threading.Event()
    main.shutdown_event = shutdown_event
    reload_thread = threading.Thread(target=schedule_config_reload, args=(shutdown_event,), daemon=True)
    reload_thread.start()
    logging.info("Configuration reload scheduler started")

    try:
        day_config = get_day_config_filename()
        logging.info(f"Starting with configuration: {day_config}")
        config = None

        while True:
            try:
                if config is None or check_for_config_changes():
                    config = load_config()
                    logging.info("Configuration reloaded")
            except Exception as e:
                logging.error(f"Failed to load configuration, retrying in 60s: {e}", exc_info=True)
                if shutdown_event.wait(timeout=60):
                    return
                continue

            if not config.times:
                logging.warning("No announcements scheduled. Retrying in 60s.")
                if shutdown_event.wait(timeout=60):
                    return
                continue

            current_time = datetime.datetime.now()
            next_announcement = calculate_next_announcement(config.times, current_time)
            if not next_announcement:
                logging.info("No upcoming announcements. Checking again in 60s.")
                if shutdown_event.wait(timeout=60):
                    return
                continue

            next_time, announcement_type = next_announcement
            sleep_seconds = (next_time - current_time).total_seconds()
            if sleep_seconds <= 0:
                continue

            if sleep_seconds > 60:
                wait_before_query = sleep_seconds - 60
                logging.info(f"Next announcement '{announcement_type}' in {sleep_seconds:.0f}s. Waiting {wait_before_query:.0f}s before fetching colors.")
                wait_start = datetime.datetime.now()
                while (datetime.datetime.now() - wait_start).total_seconds() < wait_before_query:
                    if shutdown_event.wait(timeout=min(60, wait_before_query)):
                        return
                    if check_for_config_changes():
                        logging.info("Configuration reload detected during wait")
                        break
                if check_for_config_changes():
                    continue
                logging.info("Fetching color data 1 minute before announcement...")
                color_data = get_color_message_from_db(config)
                if shutdown_event.wait(timeout=60):
                    return
            else:
                logging.info(f"Next announcement '{announcement_type}' in {sleep_seconds:.0f}s. Fetching color data immediately.")
                color_data = get_color_message_from_db(config)
                if shutdown_event.wait(timeout=sleep_seconds):
                    return

            template_mapping = {":55": "fiftyfive", "hour": "hour", "rules": "rules", "ad": "ad"}
            template_key = template_mapping.get(announcement_type, "hour")
            if announcement_type.startswith("custom:"):
                custom_name = announcement_type.replace("custom:", "")
                template_key = f"custom_{custom_name}"

            template = config.announcements.get(template_key, "Attention! It's {time}.")
            announcement_path = synthesize_announcement(template, announcement_type, next_time.strftime("%H:%M"), color_data or {}, config)
            if announcement_path:
                if not play_sound(announcement_path, config.tts['output_format']):
                    logging.error("Failed to play announcement")
            else:
                logging.error("Failed to create announcement audio")

            if shutdown_event.wait(timeout=1):
                return

    except Exception as e:
        logging.critical(f"Unhandled exception in main: {e}", exc_info=True)
        sys.exit(1)
    finally:
        shutdown_event.set()

if __name__ == "__main__":
    main()
