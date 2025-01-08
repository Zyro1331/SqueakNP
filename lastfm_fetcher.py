# Credit to a majority of this code belongs to @euphieeuphoria
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
	response = requests.get(requestURL)
	return response.json()

def getAlbumArt(jsonDict):
	#print(json.dumps(jsonDict, indent=4, sort_keys=True)) # this is just for debugging don't panic
	size_preference = ["small", "medium", "/large", "extralarge", "mega"]

	images = (jsonDict.get("album", {}).get("image", []) or jsonDict.get("track", {}).get("album", {}).get("image", []))

	available_images = {image.get("size"): image.get("#text") for image in images}

	for size in reversed(size_preference):
		if size in available_images:
			return available_images[size]

	return None

# Unused functions, for now ;3
def getLastFMPlayCount(jsonDict):
	return jsonDict.get("track", {}).get("userplaycount", 0)

def getLastFMtracklink(jsonDict):
	return jsonDict.get("track", {}).get("url", 0)

# Create global vars for rate-limiting and returning album artwork when called
previous_album_title = str("")
last_fetch: float = 0
album_art = None

async def request_album_art(config, media_propeties: MediaProperties):
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
	
	global album_art
	if skip_album_name_check:
		print("🌐 Requesting with only track data.")
		lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_propeties.artist, "track", media_propeties.title)
		album_art = getAlbumArt(lastfm_json)
		return album_art
	
	if media_propeties.album_title == str(""):
		print("❌ Failed to get Last.fm data: No Album Title was provided, skipping.")
		return None
	
	global previous_album_title
	if media_propeties.album_title == previous_album_title: 
		# Check if the album title is the same as the last one
		print("🌐 Album name is the same as before, returning the same image instead.")
		return album_art
	
	lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_propeties.album_artist, "album", media_propeties.album_title)
	album_art = getAlbumArt(lastfm_json)

	if album_art == None or album_art == str(""):
		print("🌐 Album query did not provide any results, retrying with track details instead.")
		lastfm_json = getLastFMJson(lastfm_key, lastfm_username, media_propeties.artist, "track", media_propeties.title)
		album_art = getAlbumArt(lastfm_json)
	
	if album_art == None or album_art == str(""):
		print("🌐 Album artwork couldn't be found.")
		return None
	
	previous_album_title = media_propeties.album_title
	return album_art