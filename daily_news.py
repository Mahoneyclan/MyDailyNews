#!/usr/bin/env python3
"""
My Daily News — Spotify Playlist Builder
==========================================
Automatically creates a personalised "My Daily News" playlist each morning,
containing the latest unheard episode from your priority news podcasts plus
every other podcast show you follow on Spotify.

How it works:
  1. Connects to your Spotify account using saved login credentials
  2. Fetches the latest not-yet-listened-to episode from each priority news
     podcast (Squiz Today, ABC News Daily, SBS News Headlines, The Quicky) —
     always in that order — then does the same for every other show you
     follow (saved in your Spotify library)
  3. Skips episodes older than MAX_EPISODE_AGE_DAYS, and skips episodes
     Spotify says you've already fully played
  4. Creates or overwrites a playlist called "My Daily News" in your account,
     only touching Spotify if the episode list actually changed since last run

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
# These shows are ALWAYS considered first, ALWAYS in the order listed below —
# regardless of when their episode was released (subject to the age/listened
# rules below). Every other show you follow on Spotify is appended after
# these, alphabetically by show name.
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
# Episode selection rules
# ---------------------------------------------------------------------------

# Episodes released longer ago than this are treated as stale news and never
# added to the playlist. Also used to prune old entries from history.json.
MAX_EPISODE_AGE_DAYS = 30

# How many of a show's most recent episodes to look through when the very
# latest one turns out to be already-listened-to. This lets the script fall
# back to the next-newest unheard episode instead of just giving up on a show.
EPISODE_LOOKBACK = 5

# ---------------------------------------------------------------------------
# Playlist
# ---------------------------------------------------------------------------

# The name of the Spotify playlist to create (or overwrite) each day.
# If a playlist with this exact name already exists in your account,
# its contents will be replaced. If not, a new one will be created.
PLAYLIST_NAME = "My Daily News"

# ---------------------------------------------------------------------------
# History
# Tracks which episodes have already been added to the playlist, so we can
# report what changed each run and prune stale entries. Listened-to state
# itself comes straight from Spotify (see is_fully_played below) — this file
# is just a local log, never the source of truth for "have I heard this".
# ---------------------------------------------------------------------------
HISTORY_FILE = "history.json"


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS
# These lines load the Python libraries the script needs.
# They are installed automatically when you run: pip install -r requirements.txt
# ══════════════════════════════════════════════════════════════════════════════

import json          # Reads/writes history.json
import os            # Reads environment variables (SPOTIPY_CLIENT_ID etc.) and file paths
import sys           # Lets us exit the script early if something goes wrong
import logging       # Writes timestamped log messages to the console / log file
from datetime import datetime, date, timedelta  # Dates for episode age + history pruning

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
    "user-follow-read",          # Read the artists/users you follow
    "user-library-read",         # Read the podcast shows saved/followed in your library
    "playlist-read-private",     # Read your existing playlists (to find "My Daily News")
    "playlist-modify-public",    # Create or edit public playlists
    "playlist-modify-private",   # Create or edit private playlists
    "user-read-playback-position",  # Read per-episode "fully played" status
])
# NOTE: adding scopes here means the token saved in .cache no longer covers
# everything the app needs. Spotipy detects this automatically and will
# reopen a browser window to re-authorize on the next run.


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
# HISTORY — tracks what we've added before, purely for logging/pruning.
# Listened-to state itself is read live from Spotify on every run.
# ══════════════════════════════════════════════════════════════════════════════

def load_history() -> dict:
    """Load history.json, or return an empty history if it doesn't exist yet."""
    path = os.path.join(os.path.dirname(__file__), HISTORY_FILE)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Could not read %s (%s) — starting with fresh history.", HISTORY_FILE, exc)
        return {}


def save_history(history: dict) -> None:
    path = os.path.join(os.path.dirname(__file__), HISTORY_FILE)
    with open(path, "w") as f:
        json.dump(history, f, indent=2, sort_keys=True)


def prune_history(history: dict, max_age_days: int) -> dict:
    """
    Drop history entries for episodes released more than max_age_days ago —
    keeping the file limited to a rolling window of recent news, per
    MAX_EPISODE_AGE_DAYS, instead of growing forever.
    """
    cutoff = date.today() - timedelta(days=max_age_days)
    kept = {}
    removed = 0

    for uri, entry in history.items():
        release = parse_release_date(entry.get("release_date"), entry.get("release_date_precision"))
        if release and release < cutoff:
            removed += 1
            continue
        kept[uri] = entry

    if removed:
        log.info("Pruned %d entr%s older than %d days from history.", removed, "y" if removed == 1 else "ies", max_age_days)

    return kept


# ══════════════════════════════════════════════════════════════════════════════
# PODCAST HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def parse_release_date(release_date: str | None, precision: str | None) -> date | None:
    """
    Parse a Spotify episode's release_date into a date object.
    Spotify may give day, month, or year precision — fall back gracefully.
    """
    if not release_date:
        return None

    formats = {
        "day": "%Y-%m-%d",
        "month": "%Y-%m",
        "year": "%Y",
    }
    fmt = formats.get(precision, "%Y-%m-%d")

    try:
        return datetime.strptime(release_date, fmt).date()
    except ValueError:
        # Precision claimed "day" but string doesn't match (or vice versa) — try each format.
        for fmt in formats.values():
            try:
                return datetime.strptime(release_date, fmt).date()
            except ValueError:
                continue
        return None


def is_recent(episode: dict, max_age_days: int) -> bool:
    release = parse_release_date(episode.get("release_date"), episode.get("release_date_precision"))
    if not release:
        return True  # Unknown date — don't penalise the episode, let it through.
    return release >= date.today() - timedelta(days=max_age_days)


def is_fully_played(episode: dict) -> bool:
    """Spotify's own record of whether you've already listened to this episode."""
    return bool(episode.get("resume_point", {}).get("fully_played", False))


def get_followed_show_ids(sp: spotipy.Spotify) -> list[tuple[str, str]]:
    """
    Return (show_id, show_name) for every podcast show followed/saved in the
    user's Spotify library, sorted alphabetically by name.
    """
    shows = []
    offset = 0

    while True:
        results = sp.current_user_saved_shows(limit=50, offset=offset)
        items = results.get("items", [])
        if not items:
            break

        for item in items:
            show = item.get("show", {})
            show_id = show.get("id")
            show_name = show.get("name", show_id)
            if show_id:
                shows.append((show_id, show_name))

        if not results.get("next"):
            break
        offset += len(items)

    shows.sort(key=lambda s: s[1].lower())
    return shows


def pick_episode(sp: spotipy.Spotify, show_id: str, show_name: str) -> dict | None:
    """
    Return the newest episode of a show that is both recent enough
    (MAX_EPISODE_AGE_DAYS) and not already fully played, or None if no
    such episode exists among the show's most recent EPISODE_LOOKBACK
    episodes.
    """
    try:
        results = sp.show_episodes(show_id, limit=EPISODE_LOOKBACK, market="AU")
        episodes = results.get("items", [])
    except spotipy.SpotifyException as exc:
        log.warning("Could not fetch episodes for %s: %s", show_name, exc)
        return None

    if not episodes:
        log.warning("No episodes found for: %s", show_name)
        return None

    for episode in episodes:
        if not is_recent(episode, MAX_EPISODE_AGE_DAYS):
            # Episodes are newest-first, so once we hit a stale one, older ones are stale too.
            break
        if is_fully_played(episode):
            log.info('Already listened to "%s" (%s) — checking for an older unheard episode.', episode["name"], show_name)
            continue
        log.info('Selected episode of %s: "%s"', show_name, episode["name"])
        return episode

    log.info("No unheard episode within the last %d days for: %s — skipping.", MAX_EPISODE_AGE_DAYS, show_name)
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


def get_playlist_episode_uris(sp: spotipy.Spotify, playlist_id: str) -> list[str]:
    """Return the ordered list of episode/track URIs currently in the playlist."""
    uris = []
    offset = 0

    while True:
        results = sp.playlist_items(
            playlist_id,
            fields="items(item(uri)),next",
            limit=100,
            offset=offset,
            additional_types=("track", "episode"),
        )
        items = results.get("items", [])
        if not items:
            break

        for item in items:
            # Spotify nests both tracks and episodes under "item" (not "track") in this endpoint.
            track = item.get("item") or {}
            if track.get("uri"):
                uris.append(track["uri"])

        if not results.get("next"):
            break
        offset += len(items)

    return uris


def log_playlist_changes(existing_uris: list[str], new_uris: list[str]) -> bool:
    """
    Compare what's currently in the playlist to what we're about to put there,
    logging additions/removals. Returns True if anything actually changed.
    """
    existing_set, new_set = set(existing_uris), set(new_uris)
    added = new_set - existing_set
    removed = existing_set - new_set

    if added:
        log.info("%d new episode(s) will be added to the playlist.", len(added))
    if removed:
        log.info("%d episode(s) will drop off the playlist (listened to, stale, or unfollowed).", len(removed))

    return new_uris != existing_uris


def create_or_overwrite_playlist(
    sp: spotipy.Spotify,
    user_id: str,
    uris: list[str],
) -> str:
    """
    Create "My Daily News" if it doesn't exist, then refill it with today's
    episodes — but only touch Spotify if the episode list actually changed.
    """
    playlist_id = find_existing_playlist(sp, user_id)

    if playlist_id:
        existing_uris = get_playlist_episode_uris(sp, playlist_id)
        changed = log_playlist_changes(existing_uris, uris)

        if not changed:
            log.info('Playlist "%s" already matches today\'s episodes — nothing to update.', PLAYLIST_NAME)
        else:
            log.info('Updating existing playlist "%s".', PLAYLIST_NAME)
            sp.playlist_replace_items(playlist_id, uris[:100])
            for i in range(100, len(uris), 100):
                batch = uris[i : i + 100]
                sp.playlist_add_items(playlist_id, batch)
                log.info("Added items %d–%d to playlist.", i + 1, i + len(batch))
    else:
        log.info("%d new episode(s) will be added to the playlist.", len(uris))
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
      2. Load history.json and prune entries older than MAX_EPISODE_AGE_DAYS
      3. Fetch priority podcast episodes (always first, always in order),
         then every other show the user follows (alphabetical)
      4. For each show, pick the newest episode that's recent enough and
         not already fully played — dropping shows with nothing left to add
      5. Compare against what's currently in the playlist and log the diff
      6. Create or overwrite the "My Daily News" playlist with those episodes
    """
    log.info("=== My Daily News starting — %s ===", datetime.now().strftime("%A %d %b %Y"))

    sp = authenticate()
    user_id = sp.current_user()["id"]

    history = prune_history(load_history(), MAX_EPISODE_AGE_DAYS)

    priority_ids = set(PRIORITY_PODCAST_IDS)
    shows: list[tuple[str, str]] = [
        (show_id, PRIORITY_PODCAST_NAMES.get(show_id, show_id)) for show_id in PRIORITY_PODCAST_IDS
    ]

    followed_shows = [(sid, name) for sid, name in get_followed_show_ids(sp) if sid not in priority_ids]
    log.info("Found %d followed show(s) beyond the priority list.", len(followed_shows))
    shows.extend(followed_shows)

    episode_uris: list[str] = []
    today_iso = date.today().isoformat()

    for show_id, show_name in shows:
        episode = pick_episode(sp, show_id, show_name)
        if not episode:
            continue

        uri = episode.get("uri")
        if not uri:
            continue

        episode_uris.append(uri)
        history[uri] = {
            "show": show_name,
            "episode_name": episode.get("name"),
            "release_date": episode.get("release_date"),
            "release_date_precision": episode.get("release_date_precision"),
            "added_date": today_iso,
        }

    save_history(history)

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
