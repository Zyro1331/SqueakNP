import asyncio
import enum
import configparser
from rich import print
from pythonosc import udp_client
from time import sleep
import time
import lastfm_fetcher
import os
import shutil

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionMediaProperties as MediaProperties,
    GlobalSystemMediaTransportControlsSessionTimelineProperties as TimelineProperties
)

class PlaybackStatusEnum(enum.IntEnum):
    CLOSED = 0
    OPENED = 1
    CHANGING = 2
    STOPPED = 3
    PLAYING = 4
    PAUSED = 5

client = None
config = None
last_send_to_vrchat: float = 0

def read_config(config_file):
    config = configparser.ConfigParser()
    try:
      config.read(config_file)
      return config
    except Exception as e:
        print(f"Error reading config file: {e}")

def start_osc_client():
    global config
    send_addr: str = config.get('send', "address", fallback="127.0.0.1") 
    send_port: int = config.getint('send', "port", fallback=9025)

    try:
        global client
        client = udp_client.SimpleUDPClient(send_addr, send_port)
        print(f"🔊 Started OSC Client @ {send_addr}:{send_port}")
    except Exception as e:
        print(f"OSC Client Error: {e}")

async def monitor_media_changes():
    sessions = await MediaManager.request_async()
    current_session = sessions.get_current_session()

    # If there's no active multimedia session, wait a little longer until something happens
    if current_session == None:
        print("⏳ No current playback session detected, waiting for input.")
        while current_session == None:
            sessions = await MediaManager.request_async()
            current_session = sessions.get_current_session()
            await asyncio.sleep(3)
    
    # Write variables from Config
    global config
    refresh_rate: float = config.getfloat('squeak', "refresh_rate", fallback=1) 
    useLastFM: bool = config.getboolean('last_fm', "enabled", fallback=False)
    useVRChatbox: bool = config.getboolean('vrchat', "enabled", fallback=False)    

    if current_session:
        previous_title = None
        previous_playback_status = None

        session_app_id = current_session.source_app_user_model_id
        print(f"✅ Connected to playback session: {session_app_id}")

        while True:
            try:
                # Initalize the global client variable and get all required information from SMTC
                global client
                media_properties = await current_session.try_get_media_properties_async()
                session_playback_info = current_session.get_playback_info()
                media_timeline_properties = current_session.get_timeline_properties()
                current_title = media_properties.title

                # Broadcast and print out text metadata when it changes
                if current_title != previous_title and current_title != str(""):
                    print(f"Now Playing: \n:notes: {media_properties.title} \n:microphone: {media_properties.artist} \n:cd: {media_properties.album_title}")
                    client.send_message('/squeaknp/track_title', f"{media_properties.title}")
                    client.send_message('/squeaknp/track_artist', f"{media_properties.artist}")
                    client.send_message('/squeaknp/track_album', f"{media_properties.album_title}")
                    previous_title = current_title

                    # Album Art Fetching
                    if useLastFM:
                        print("🌐 Querying Last.fm for metadata")
                        try: 
                            album_artwork_url, lastfm_track_url, lastfm_playcount = await lastfm_fetcher.query_lastfm_data(config, media_properties)
                        except Exception as e: print(f"Last.fm fetcher error: {e}") 
                        
                        client.send_message('/squeaknp/lastfm_album_art', f"{album_artwork_url}")
                        client.send_message('/squeaknp/lastfm_url', f"{lastfm_track_url}")
                        client.send_message('/squeaknp/lastfm_playcount', lastfm_playcount)

                if useLastFM:
                    # Resubmit the Album Art each update to work around a strange Resonite bug that nulls the value at random
                    if album_artwork_url != None: client.send_message('/squeaknp/lastfm_album_art', f"{album_artwork_url}")

                # Check for playback state changes
                playback_status = session_playback_info.playback_status
                if playback_status != previous_playback_status:
                    print(f"⏯️ Playback status changed: {get_enum_name_by_value(PlaybackStatusEnum, playback_status)}")
                    client.send_message('/squeaknp/playback_state', f"{get_enum_name_by_value(PlaybackStatusEnum, playback_status)}")
                    client.send_message('/squeaknp/playback_state_int', playback_status)
                    previous_playback_status = playback_status
                
                # Prevent dividing by zero multiple times if an application does not give playback data
                if media_timeline_properties.position.total_seconds() != 0 or media_timeline_properties.end_time.total_seconds() != 0: 
                    normalized_playback_position = media_timeline_properties.position.total_seconds() / media_timeline_properties.end_time.total_seconds()

                # Submit Timeline Positions
                client.send_message('/squeaknp/timeline_position', media_timeline_properties.position.total_seconds())
                client.send_message('/squeaknp/timeline_end_time', media_timeline_properties.end_time.total_seconds())
                client.send_message('/squeaknp/timeline_position_timecode', timedelta_to_hms_short(media_timeline_properties.position))
                client.send_message('/squeaknp/timeline_end_time_timecode', timedelta_to_hms_short(media_timeline_properties.end_time))
                client.send_message('/squeaknp/timeline_normalized_position', normalized_playback_position)
            
                if useVRChatbox and playback_status == 4: vrchat_chatbox_sender(media_properties, media_timeline_properties)

            # Tell the user if something explodes and end the loop
            except Exception as e:
                print(f"Error: {e}")
                break
            
            await asyncio.sleep(refresh_rate)

def vrchat_chatbox_sender(media_info: MediaProperties, timeline_info: TimelineProperties):
    # Rate-limit the amount of chatbox sends to VRChat to prevent further in-game ratelimiting. 
    global last_send_to_vrchat
    time_elapsed = time.time() - last_send_to_vrchat
    if time_elapsed > 8: 
        last_send_to_vrchat = time.time()
        #textbox_format: str = config.get('vrchat', "chatbox_config", fallback="SqueakNP: No string for chatbox data could be found.")
        text_output: str = str(f"Listening to:\n{media_info.title} - {media_info.artist}\n{timedelta_to_hms_short(timeline_info.position)} / {timedelta_to_hms_short(timeline_info.end_time)}")
        client.send_message('/chatbox/input', [text_output, True, False])

def get_enum_name_by_value(enum_class, value):
    for member in enum_class:
        if member.value == value:
            return member.name
    return None

def timedelta_to_hms_short(td):
  hours, remainder = divmod(td.seconds, 3600)
  minutes, seconds = divmod(remainder, 60)

  time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

  # Shorten the string
  if hours == 0:
    time_str = time_str[3:]  # Remove hours
    if seconds == 0:
      return f"{minutes:02d}:00"  # Keep minutes even if 0
    return f"{minutes:02d}:{seconds:02d}" 

  return time_str

def create_config_file(config_path):
    try: shutil.copy("plates/config_template.cfg", config_path)
    except Exception as e: print(f"Error creating config: {e}")
    print(f"Created new config file at: {config_path}")

def init_squeak():
    print("Initalizing...")
    config_path = "squeakconfig.cfg"
    if os.path.exists(config_path):
        print("Loading config...")
        pass
    else:
        print(f"No config file found, creating a new one...")
        create_config_file(config_path)
    global config
    try: config = read_config(config_path)
    except Exception as e: print(f"Error reading config: {e}")

if __name__ == "__main__":
    init_squeak()
    print("Squeak! 🦇")
    start_osc_client()
    while True: # Restart the loop if it breaks due to errors or the RPC being unexpectedly closed
        asyncio.run(monitor_media_changes())
        print("🔄️ Restarting SMTC Monitor")
        sleep(1)