import argparse
import requests
import os
import subprocess as sb
import sys
import json
from mutagen.mp4 import MP4, MP4Cover
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
        

OUTPUT_DIR = "/app/music" # same as Dockerfile

class Downloader:

    def __init__(self, output_dir: str):
        self.OUTPUT_DIR = output_dir

        self.SPOTIFY_BASE_URL = "https://api.spotify.com/v1"

        self._parse_config()

        self.ACCESS_TOKEN = self._get_access_token()
        self.headers = {
            "Authorization": f"Bearer {self.ACCESS_TOKEN}"
        }

    def _parse_config(self):
        with open('config.json', 'r') as file:
            config = json.load(file)
        self._SPOTIFY_CLIENT_ID = config['spotify_client_id']
        self._SPOTIFY_CLIENT_SECRET = config['spotify_client_secret']

    def download_song(self, track_id: str, skip_if_exists: bool = False, custom_yt_url: str = None):
        try:
            print("Searching song on Spotify")
            track_data = self._get_track_data(track_id)
        except APIClientException as e:
            print(e.message)
            print(TermColors.FAIL + "Fatal exception. Program will now exit.")
            sys.exit(0)

        filename = f"{self.OUTPUT_DIR}/{self._create_search_term(track_data, escape_chars=False)}.m4a"

        if os.path.exists(filename) and skip_if_exists == True:
            print(TermColors.OKBLUE + f"{track_data['track_name']} already exists. Skipping download...")
        else:
            filename = self._download_from_yt(track_data, custom_yt_url=custom_yt_url)
            if filename != None:            
                self._embed_metadata(filename, track_data)

    def _get_playlist_data(self, playlist_id: str, next_url: str = None):
        if next_url == None:
            url = f"{self.SPOTIFY_BASE_URL}/playlists/{playlist_id}"
        else:
            url = next_url

        resp = requests.get(url, headers=self.headers)

        if resp.status_code >= 400:
            error_message = resp.json().get('error', {}).get('message', 'Unknown error occurred.')
            raise APIClientException(f"Error: {resp.status_code} - {error_message}")

        data = resp.json()
        return data

    def _search_playlist(self, playlist_id: str):
        print("Searching playlist on Spotify")
        data = self._get_playlist_data(playlist_id)
        print(TermColors.OKGREEN + f"Playlist {data['name']} found. Parsing...")
        items  = data['tracks']['items']
        print(TermColors.OKGREEN + f"{data['tracks']['total']} songs found.")

        next_url = data['tracks']['next']
        page = 2 # Page 1 was already manually searched above, so we start from 2.
        while next_url != None:
            print(f"Searching page {page}...")
            data = self._get_playlist_data(playlist_id, next_url=next_url)
            items += data['items']
            next_url = data['next']
        print(f"{len(items)} songs scraped.")
        return data, items

    def download_playlist(self, playlist_id: str):
        data, items = self._search_playlist(playlist_id)
        for item in items:
            track = item['track']
            print(TermColors.OKGREEN + f"Downloading {track['name']}")

            self.download_song(track['id'], skip_if_exists=True)
            print(TermColors.OKCYAN + f"{track['name']} Finished.")
            print("========================================")

    def sync_playlist(self, playlist_id: str):
        data, items = self._search_playlist(playlist_id)
        missing_tracks = []

        print("Syncing...")
        for item in items:
            track = item['track']
            track_data = self._get_track_data(track['id'])
            search_term = self._create_search_term(track_data, escape_chars=False)
            filename = f"{self.OUTPUT_DIR}/{search_term}.m4a"

            if os.path.exists(filename):
                print(TermColors.OKBLUE + f"{search_term} already exists.")
            else:
                missing_tracks.append(track_data)
                print(TermColors.WARNING + f"{search_term} does not exist.")

        try:
            print(TermColors.OKGREEN + f"Finished syncing.\nTotal tracks: {data['tracks']['total']}\nMissing songs: {len(missing_tracks)}")
        except KeyError:
            print(TermColors.OKGREEN + f"Finished syncing.\nTotal tracks: {data['total']}\nMissing songs: {len(missing_tracks)}")


        if len(missing_tracks) == 0:
            print(TermColors.OKGREEN + "All tracks already exist on your computer. Congratulations! :)")
            sys.exit(0)

        for i, track in enumerate(missing_tracks, start=1):
            print(f"{i}) {track['track_name']} - {' '.join(track['artist_names'])}")

        tracks_to_download = input("Enter numbers of tracks to download (comma-separated). For example, '1,3'\n")
        tracks = []

        for i in tracks_to_download.split(','):
            try:
                tracks.append(missing_tracks[int(i)-1])
            except ValueError:
                print(TermColors.FAIL + "Invalid input...")
                sys.exit(0)
        
        print(TermColors.OKGREEN + "Downloading selected tracks.")
        for track in tracks:
            print("Searching song on Spotify")
            # search_term = self._create_search_term(track)
            filename = self._download_from_yt(track)
            if filename != None:            
                self._embed_metadata(filename, track)

    def _get_access_token(self):
        token_url = 'https://accounts.spotify.com/api/token'
        client_id = self._SPOTIFY_CLIENT_ID
        client_secret = self._SPOTIFY_CLIENT_SECRET
        
        oauth = OAuth2Session(client=BackendApplicationClient(client_id=client_id))
        token = oauth.fetch_token(token_url=token_url, client_id=client_id, client_secret=client_secret)
        
        access_token = token['access_token']
        return access_token

    def _get_track_data(self, track_id):
        url = f"{self.SPOTIFY_BASE_URL}/tracks/{track_id}"
    
        response = requests.get(url, headers=self.headers)
        if response.status_code >= 400:
            error_message = response.json().get('error', {}).get('message', 'Unknown error occurred.')
            raise APIClientException(f"Error: {response.status_code} - {error_message}")
    
        data = response.json()
        album_type = data['album']['album_type']
        album_name = data['album']['name']
        album_release_date = data['album']['release_date']
        artist_names = [artist['name'] for artist in data['artists']]
        duration_ms = data['duration_ms']
        track_id = data['id']
        track_name = data['name']
        images = [image['url'] for image in data['album']['images'] if image['width'] == 300]
    
        return {
            'album_type': album_type,
            'album_name': album_name,
            'album_release_date': album_release_date,
            'artist_names': artist_names,
            'duration_ms': duration_ms,
            'track_id': track_id,
            'track_name': track_name,
            'images': images
        }
    
    def _download_from_yt(self, track_data: dict, custom_yt_url: str = None):
        search_term = self._create_search_term(track_data)
        if custom_yt_url == None:
            print(TermColors.OKCYAN + "Searching song on ytfzf. Please select the correct video.")
            print(f"Search term: {search_term}")
            yt_url = os.popen(f"ytfzf -L {search_term}").read()
        else:
            print(TermColors.OKCYAN + "Using custom YouTube url.")
            yt_url = custom_yt_url

        print("Link: " + yt_url)
        
        print(TermColors.OKGREEN + "Downloading with yt-dlp...")
        _backslash = '\\'
        filename = self._create_search_term(track_data, escape_chars=False)
        filepath = f"{self.OUTPUT_DIR}/{filename}.m4a"
        print(f"Filepath: {filepath}")

        ytdlp_output = sb.Popen(['yt-dlp', '-f', '140', '-o', filepath, yt_url], stdout=sb.PIPE, stderr=sb.PIPE)
        stdout, stderr = ytdlp_output.communicate()

        if stderr.decode('utf-8').startswith("ERROR"):
            print(TermColors.FAIL + f"An error occurred with yt-dlp while downloading the video. Please see the output below. Skipping this song: {search_term}")
            print(TermColors.FAIL + stderr.decode('utf-8'))
            return None

        print(TermColors.OKGREEN + "Finished download")
        return filepath
    
    def _create_search_term(self, track_data, escape_chars: bool = True):
        search_term = track_data['track_name'] + ' - ' + ' '.join(track_data['artist_names'])
        if escape_chars == True:
            search_term = search_term.replace("(", "\(")
            search_term = search_term.replace(")", "\)")
            search_term = search_term.replace("'", r"\'")
            search_term = search_term.replace("\"", r'\"')
            search_term = search_term.replace("&", "\&")
        return search_term

    def _embed_metadata(self, filename, metadata):
        print(TermColors.OKGREEN + f"Adding metadata to song: {filename} ")
        audio_file = MP4(filename)
        meta = audio_file.tags
        meta.clear()
        
        # Find the tag names in the official mutagen docs: https://mutagen.readthedocs.io/en/latest/api/mp4.html#mutagen.mp4.MP4Tags
        meta['\xa9nam'] = metadata['track_name']
        meta['\xa9ART'] = ', '.join(metadata['artist_names'])
        meta['\xa9alb'] = metadata['album_name']
        meta['\xa9day'] = metadata['album_release_date']
        meta['\xa9cmt'] = metadata['track_id']
        
        img_resp = requests.get(metadata['images'][0])
        if img_resp.status_code == 200:
            meta['covr'] = [
                MP4Cover(img_resp.content, imageformat=MP4Cover.FORMAT_JPEG)
            ]
    
        meta.save(filename)
        print(TermColors.OKGREEN + f"Metadata added and saved: {filename}")
    

class CommandLineParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "Command line utility for Spotify Downloader app."

        self.add_argument('type', help="Specify what you're downloading. Either 'track' or 'playlist'.")
        self.add_argument('id', help="The playlist/track ID from Spotify.")
        self.add_argument('-s', '--sync', action='store_true', help='If true, it will check your tracks and identify missing ones, then let you download the missing songs. To use this, the given ID MUST be a playlist.')
        self.add_argument('-yt', "--youtube-url", help="Specify your own URL for which YouTube video to download. Can be helpful if the program is not showing you the correct video in search results. This option ONLY works when downloading individual tracks.")

        args = self.parse_args()
        self.spotify = self.get_spotify_id()
        self.sync = args.sync
        self.yt_url = args.youtube_url

    def get_spotify_id(self):
        args = self.parse_args()
        return {
                "type": args.type,
                "id": args.id
            }

class APIClientException(Exception):
    """
    This exception will be raised when the Spotify API returns an error.
    """

    def __init__(self, message):
        self.message = message


class TermColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

client = Downloader(OUTPUT_DIR)
parser = CommandLineParser()

if parser.spotify['type'] == 'playlist':
    if parser.sync == True:
        client.sync_playlist(parser.spotify['id'])
    else:
        client.download_playlist(parser.spotify['id'])
elif parser.spotify['type'] == 'track':
    client.download_song(parser.spotify['id'], custom_yt_url=parser.yt_url)
else:
    print(TermColors.FAIL + "Invalid 'type' specified.")

