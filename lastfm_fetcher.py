# Credit to a majority of this code belongs to @euphieeuphoria on Discord
# He graciously let me borrow the album-art fetching from his own iTunes script with Last.fm support

import requests
from urllib.parse import quote
import time
import json
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionMediaProperties as MediaProperties,
)

def getLastFMJson(lastFMKey, lastFMusername, artist, reqType, req):
	# Last.fm apparently gets really upset with the keywords below, so make sure they're scrubbed from the request.
	#remove - Single
	req = req.replace("- Single","")

	#remove - EP
	req = req.replace("- EP","")

	requestURL = f'https://ws.audioscrobbler.com/2.0/?method={reqType}.getInfo&api_key={lastFMKey}&artist={quote(artist)}&{reqType}={quote(req)}&autocorrect=0&username={lastFMusername}&format=json'
	
	try: response = requests.get(requestURL)
	except requests.exceptions.HTTPError as errh:
		print(f"HTTP Error: {errh}")
	except requests.exceptions.ConnectionError as errc:
		print(f"Connection Error: {errc}")
	except requests.exceptions.Timeout as errt:
		print(f"Timeout Error: {errt}")
	except Exception as err:
		print(f"Something went wrong: {err}")
	else:
		# print(requestURL) # Debug
		# print(json.dumps(response.json(), indent=4)) # Debug
		return response.json()

def getSongDetails(jsonDict):
	# Last.fm Track URL Fetching
	lastfm_track_url = jsonDict.get("track", {}).get("url", "") or jsonDict.get("album", {}).get("url", "") or jsonDict.get("artist", {}).get("url", "")

	# Get the user's playcount if they desire
	lastfm_playcount = jsonDict.get("track", {}).get("userplaycount", 0)

	return lastfm_track_url, lastfm_playcount

# Create global vars for rate-limiting and returning album artwork when called
previous_album_title = str("")
last_fetch: float = 0
album_art = None

def request_album_art(lastfm_json: json, media_propeties: MediaProperties):
	global album_art
	global previous_album_title

	if media_propeties.album_title == previous_album_title and not previous_album_title == "": 
		# Check if the album title is the same as the last one
		print("🌐 Album name is the same as before, returning the same image instead.")
		return album_art

	size_preference = ["small", "medium", "/large", "extralarge", "mega"]

	images = (lastfm_json.get("album", {}).get("image", []) or lastfm_json.get("track", {}).get("album", {}).get("image", []))

	available_images = {image.get("size"): image.get("#text") for image in images}

	for size in size_preference:
		if size in available_images:
			album_art = available_images[size]

	if album_art == None or album_art == str(""):
		print("🌐 Found details on Last.fm, but no artwork was found.")
		return str("")
	
	print(f"🌐 Found album artwork: {album_art}")

	previous_album_title = media_propeties.album_title
	return album_art

async def query_lastfm_data(config, media_properties: MediaProperties):
	lastfm_key = config.get('last_fm', "last_fm_api_key")
	lastfm_username = config.get('last_fm', "last_fm_username")
	skip_album_name_check = config.getboolean('last_fm', "use_track_titles_only", fallback=False)

	global last_fetch # Handle ratelimiting
	time_elapsed: float = time.time() - last_fetch
	if time_elapsed < 3:
		print("❌ Failed to get Last.fm data: Rate-limit protection active, please wait 10 seconds before querying again.")
		return None
	last_fetch = time.time()

	if lastfm_key == None or lastfm_username == None: # If nothing was provided in the config file, don't try to query any data.
		print("❌ Failed to get Last.fm data: No Username or API Key was provided.")
		return None
	
	if skip_album_name_check: lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_properties.artist, "track", media_properties.title)
	else: lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_properties.album_artist, "album", media_properties.album_title)

	if "error" in lastfm_json: # When something explodes, try again. It'll surely not explode again, right?
		if lastfm_json.get("error") == 6 and not skip_album_name_check:
			print("🌐 Album query did not provide any results, retrying with track details instead.")
			lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_properties.artist, "track", media_properties.title)
			if "error" in lastfm_json:
				print(f"❌ An error occured while fetching from Last.fm: {lastfm_json.get("message")}")
				return None
		else:
			print(f"❌ An error occured while fetching from Last.fm: {lastfm_json.get("message")}")
			return None
	
	album_art = request_album_art(lastfm_json, media_properties) # Yoink the album artwork if it's found
	track_url, playcount = getSongDetails(lastfm_json) # Get stuff like the Last.fm URL when avalible.

	return album_art, track_url, playcount