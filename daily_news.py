#!/usr/bin/env python3
"""
My Daily News — Spotify Playlist Builder
==========================================
Automatically creates a personalised "My Daily News" playlist each morning,
containing the latest episode from a fixed list of Australian news podcasts.

How it works:
  1. Connects to your Spotify account using saved login credentials
  2. Fetches the latest episode from each priority news podcast
     (Squiz Today, ABC News Daily, SBS News Headlines, The Quicky) —
     always in that order
  3. Creates or overwrites a playlist called "My Daily News" in your account

Run manually:  python3 daily_news.py
Scheduled:     runs automatically at 5:00 AM daily via LaunchAgent
Log file:      daily_news.log (in this folder — check here if something goes wrong)
"""

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# Edit the values in this section to customise your playlist.
# Everything else in the file can be left as-is.
# ══════════════════════════════════════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Priority podcasts
# These shows are ALWAYS included, ALWAYS in the order listed below —
# regardless of when their episode was released.
#
# To find a show's Spotify ID:
#   1. Open the show in the Spotify app
#   2. Click the three-dot menu → Share → Copy link to show
#   3. The link looks like: https://open.spotify.com/show/1D4A4NKKF0axPvAS7h31Lu
#   4. The ID is the long string at the end (after "/show/")
#
# To add a new show: paste its ID as a new line inside the list below.
# To remove a show: delete its line.
# To reorder:       move the lines around — top of the list = first in playlist.
# ---------------------------------------------------------------------------
PRIORITY_PODCAST_IDS = [
    "0B7f89Byi1DjBTIQH4h0t2",  # Squiz Today
    "1D4A4NKKF0axPvAS7h31Lu",  # ABC News Daily
    "0jg3AfXsIV2WBvw4oGgFFW",  # SBS News Headlines
    "4omeoOVsGWXhhFObFWGTvT",  # The Quicky
]

# Friendly display names for each priority podcast.
# These are only used in log messages so you can see what's happening.
# Keep this in sync with PRIORITY_PODCAST_IDS above.
PRIORITY_PODCAST_NAMES = {
    "0B7f89Byi1DjBTIQH4h0t2": "Squiz Today",
    "1D4A4NKKF0axPvAS7h31Lu": "ABC News Daily",
    "0jg3AfXsIV2WBvw4oGgFFW": "SBS News Headlines",
    "4omeoOVsGWXhhFObFWGTvT": "The Quicky",
}

# ---------------------------------------------------------------------------
# Playlist
# ---------------------------------------------------------------------------

# The name of the Spotify playlist to create (or overwrite) each day.
# If a playlist with this exact name already exists in your account,
# its contents will be replaced. If not, a new one will be created.
PLAYLIST_NAME = "My Daily News"


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS
# These lines load the Python libraries the script needs.
# They are installed automatically when you run: pip install -r requirements.txt
# ══════════════════════════════════════════════════════════════════════════════

import os           # Reads environment variables (SPOTIPY_CLIENT_ID etc.)
import sys          # Lets us exit the script early if something goes wrong
import logging      # Writes timestamped log messages to the console / log file
from datetime import datetime  # Used to get today's date and format timestamps

import spotipy                      # The main Spotify API library
from spotipy.oauth2 import SpotifyOAuth  # Handles the Spotify login / token flow
from dotenv import load_dotenv      # Reads our credentials from the .env file


# ══════════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# LOAD CREDENTIALS
# The script reads your Spotify app credentials from environment variables.
# These are set in the .env file in this folder (never committed to GitHub).
#
# Required variables:
#   SPOTIPY_CLIENT_ID      — from your Spotify Developer Dashboard
#   SPOTIPY_CLIENT_SECRET  — from your Spotify Developer Dashboard
#   SPOTIPY_REDIRECT_URI   — must be http://127.0.0.1:8888/callback
# ══════════════════════════════════════════════════════════════════════════════

load_dotenv()

REQUIRED_ENV_VARS = ["SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", "SPOTIPY_REDIRECT_URI"]
missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
if missing:
    log.error(
        "Missing required environment variables: %s\n"
        "Copy .env.example to .env and fill in your Spotify credentials.",
        ", ".join(missing),
    )
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# SPOTIFY PERMISSION SCOPES
# ══════════════════════════════════════════════════════════════════════════════

SCOPES = " ".join([
    "user-follow-read",      # Read the podcasts and artists you follow
    "playlist-read-private", # Read your existing playlists (to find "My Daily News")
    "playlist-modify-public",  # Create or edit public playlists
    "playlist-modify-private", # Create or edit private playlists
])


# ══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════

def authenticate() -> spotipy.Spotify:
    """
    Log in to Spotify and return an authenticated client object.

    On the FIRST run: opens a browser window so you can log in to Spotify
    and grant the app permission. After you approve, the token is saved to
    a file called .cache in this folder.
    On SUBSEQUENT runs (including LaunchAgent): reads the token from .cache
    and refreshes it automatically. No browser needed.
    """
    log.info("Authenticating with Spotify …")
    try:
        auth_manager = SpotifyOAuth(
            scope=SCOPES,
            cache_path=os.path.join(os.path.dirname(__file__), ".cache"),
            open_browser=True,
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
        user = sp.current_user()
        log.info("Authenticated as: %s (%s)", user["display_name"], user["id"])
        return sp

    except Exception as exc:
        log.error("Authentication failed: %s", exc)
        log.error(
            "Check that SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and "
            "SPOTIPY_REDIRECT_URI are set correctly in your .env file, and that "
            "the redirect URI is registered in your Spotify Developer Dashboard."
        )
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# PODCAST HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def get_latest_episode(sp: spotipy.Spotify, show_id: str, show_name: str = "") -> dict | None:
    """
    Fetch and return the single most recent episode of a podcast.

    The 'market="AU"' parameter tells Spotify to return content available
    in Australia. Remove or change this if you're in a different country.
    """
    label = show_name or show_id

    try:
        results = sp.show_episodes(show_id, limit=1, market="AU")
        episodes = results.get("items", [])

        if not episodes:
            log.warning("No episodes found for: %s", label)
            return None

        episode = episodes[0]
        log.info('Latest episode of %s: "%s"', label, episode["name"])
        return episode

    except spotipy.SpotifyException as exc:
        log.warning("Could not fetch episodes for %s: %s", label, exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PLAYLIST BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def find_existing_playlist(sp: spotipy.Spotify, user_id: str) -> str | None:
    """
    Look through the user's playlists for one named PLAYLIST_NAME that they own.
    Returns the playlist ID if found, or None if it doesn't exist yet.
    """
    offset = 0

    while True:
        results = sp.current_user_playlists(limit=50, offset=offset)
        items = results.get("items", [])

        if not items:
            return None

        for pl in items:
            if pl.get("name") == PLAYLIST_NAME and pl.get("owner", {}).get("id") == user_id:
                return pl["id"]

        if not results.get("next"):
            return None
        offset += len(items)


def create_or_overwrite_playlist(
    sp: spotipy.Spotify,
    user_id: str,
    uris: list[str],
) -> str:
    """
    Create "My Daily News" if it doesn't exist, then fill it with today's episodes.
    If the playlist already exists (from a previous day), clear it and refill it.
    """
    playlist_id = find_existing_playlist(sp, user_id)

    if playlist_id:
        log.info('Found existing playlist "%s" — clearing it.', PLAYLIST_NAME)
        sp.playlist_replace_items(playlist_id, [])
    else:
        log.info('Creating new playlist "%s" …', PLAYLIST_NAME)
        pl = sp._post(
            "me/playlists",
            payload={
                "name": PLAYLIST_NAME,
                "public": False,
                "description": f"Auto-generated by My Daily News on {datetime.now().strftime('%d %b %Y')}",
            },
        )
        playlist_id = pl["id"]

    for i in range(0, len(uris), 100):
        batch = uris[i : i + 100]
        sp.playlist_add_items(playlist_id, batch)
        log.info("Added items %d–%d to playlist.", i + 1, i + len(batch))

    playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
    log.info("Playlist ready: %s", playlist_url)
    return playlist_url


# ══════════════════════════════════════════════════════════════════════════════
# MAIN — ties everything together
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Entry point — runs all the steps in order to build today's playlist.

    Steps:
      1. Authenticate with Spotify
      2. Fetch priority podcast episodes (Squiz Today, ABC News Daily,
         SBS News Headlines, The Quicky)
      3. Create or overwrite the "My Daily News" playlist with those episodes
    """
    log.info("=== My Daily News starting — %s ===", datetime.now().strftime("%A %d %b %Y"))

    sp = authenticate()
    user_id = sp.current_user()["id"]

    episode_uris: list[str] = []

    for show_id in PRIORITY_PODCAST_IDS:
        show_name = PRIORITY_PODCAST_NAMES.get(show_id, show_id)
        episode = get_latest_episode(sp, show_id, show_name)

        if not episode:
            log.warning(
                "Could not fetch episode for %s — skipping. "
                "Check the show ID in PRIORITY_PODCAST_IDS at the top of this script.",
                show_name,
            )
            continue

        uri = episode.get("uri")
        if uri:
            episode_uris.append(uri)

    if not episode_uris:
        log.error(
            "No podcast episodes found at all. "
            "Check your show IDs and that your credentials are correct."
        )
        sys.exit(1)

    playlist_url = create_or_overwrite_playlist(sp, user_id, episode_uris)

    log.info(
        "Playlist will contain %d episode(s).", len(episode_uris),
    )
    log.info("=== Done! Open your playlist: %s ===", playlist_url)


if __name__ == "__main__":
    main()
