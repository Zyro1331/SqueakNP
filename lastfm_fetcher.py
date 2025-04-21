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
	req = req.replace("- Single","")
	req = req.replace("- EP","")

	requestURL = f'https://ws.audioscrobbler.com/2.0/?method={reqType}.getInfo&api_key={lastFMKey}&artist={quote(artist)}&{reqType}={quote(req)}&autocorrect=0&username={lastFMusername}&format=json'
	
	try: response = requests.get(requestURL)
	except requests.exceptions.HTTPError as errh:
		raise(f"HTTP Error: {errh}")
	except requests.exceptions.ConnectionError as errc:
		raise(f"Connection Error: {errc}")
	except requests.exceptions.Timeout as errt:
		raise(f"Timeout Error: {errt}")
	except Exception as err:
		raise(f"Request Failed: {err}")
	else:
		# print(requestURL) # Debug
		# print(json.dumps(response.json(), indent=4)) # Debug
		return response.json()

def getSongDetails(jsonDict):
	# Last.fm Track URL Fetching
	lastfm_track_url = jsonDict.get("track", {}).get("url", "") or jsonDict.get("album", {}).get("url", "") or jsonDict.get("artist", {}).get("url", "")
	print(f"🌐 Last.fm url found: {lastfm_track_url}")

	# Get the user's playcount if they desire
	lastfm_playcount = jsonDict.get("track", {}).get("userplaycount", 0)

	return lastfm_track_url, lastfm_playcount

# Create global vars for rate-limiting and returning album artwork when called
previous_album_title = str("")
last_fetch: float = 0
album_art = None

def get_album_art(lastfm_json: json, media_propeties: MediaProperties):
	global album_art
	global previous_album_title

	if media_propeties.album_title == previous_album_title and not previous_album_title == "": 
		# Check if the album title is the same as the last one
		print(f"🌐 Album name is the same as before, returning the same image instead: {album_art}")
		return album_art
	
	# Empty the album art variable so if nothing is found, it doesn't return the same artwork from the previous track.
	album_art = None 

	# Collect image results from query and list them.
	size_preference = ["small", "medium", "/large", "extralarge", "mega"]
	images = (lastfm_json.get("album", {}).get("image", []) or lastfm_json.get("track", {}).get("album", {}).get("image", []))
	available_images = {image.get("size"): image.get("#text") for image in images}

	for size in size_preference:
		if size in available_images:
			album_art = available_images[size]

	# If the album artwork returns nothing, then just return nothing.
	if album_art == None or album_art == str(""):
		return str("")
	
	print(f"🌐 Found album artwork: {album_art}")

	previous_album_title = media_propeties.album_title
	return album_art

async def query_lastfm_data(config, media_properties: MediaProperties):
	# Get preferences from config file
	lastfm_key = config.get('last_fm', "last_fm_api_key")
	lastfm_username = config.get('last_fm', "last_fm_username")

	# Prevent API Ratelimiting by supplying my own.
	global last_fetch 
	time_elapsed: float = time.time() - last_fetch
	ratelimit: int = 3
	if time_elapsed < ratelimit:
		raise ValueError(f"Rate-limit protection active, please wait {ratelimit} seconds before querying again.")
	last_fetch = time.time()

	if lastfm_key == None or lastfm_username == None: # If nothing was provided in the config file, don't try to query any data.
		raise ValueError("No Username or API Key was provided.")

	# Request metadata via Track Information
	lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_properties.artist, "track", media_properties.title)

	# If there's nothing provided by the album details, try it again with only track info.
	if lastfm_json.get("error") == 6 and media_properties.album_title != str(""): 
		print("🌐 Track query did not provide any results, retrying with album title instead.")
		lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_properties.album_artist, "album", media_properties.album_title)

	if "error" in lastfm_json:
		raise ValueError(lastfm_json.get("message"))
	
	track_url, playcount = getSongDetails(lastfm_json) # Get stuff like the Last.fm URL when avalible.
	album_art = get_album_art(lastfm_json, media_properties) # Fetch album artwork

	# Second-chance album-artwork fetch just to see if it's possible.
	if album_art == str("") and media_properties.album_title != str(""):
		print("🌐 Couldn't find artwork, so retrying search with album title instead as a second-attempt.")
		lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_properties.album_artist, "album", media_properties.album_title)
		if "error" in lastfm_json:
			print("❌ Second-attempt fetch for album artwork failed.")
		else:
			album_art = get_album_art(lastfm_json, media_properties)
			if album_art == str(""):
				print("❌ Second-attempt fetch for album artwork failed.")

	return album_art, track_url, playcount