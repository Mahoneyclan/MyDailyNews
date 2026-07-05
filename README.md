# My Daily News

Automatically builds a personalised **My Daily News** playlist in your Spotify account each morning, containing the latest episode from a fixed list of Australian news podcasts.

Default behaviour:
- Fetches the latest episode from 4 priority Australian news podcasts, always in this order:
  1. Squiz Today
  2. ABC News Daily
  3. SBS News Headlines
  4. The Quicky
- Creates or overwrites a private playlist called **My Daily News**
- Runs automatically at **5:00 AM** daily via LaunchAgent

This project is a sibling of [MyDailyDrive](https://github.com/Mahoneyclan/MyDailyDrive) — MyDailyDrive now focuses on a single news podcast (ABC News Top Stories) mixed with music, while MyDailyNews carries the full daily news roundup that used to live there.

---

## Prerequisites

- macOS (tested on Mac Mini M1)
- Python 3.11 or later — check with `python3 --version`
- A free [Spotify Developer account](https://developer.spotify.com/)

---

## Step 1 — Create a Spotify Developer App

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in.
2. Click **Create app**.
3. Fill in any **App name** and **App description** (e.g. "My Daily News").
4. In the **Redirect URIs** field enter exactly:
   ```
   http://127.0.0.1:8888/callback
   ```
   Click **Add** so it appears in the list, then click **Save**.
5. Open your new app and go to **Settings**. Copy the **Client ID** and **Client Secret** — you will need them in Step 3.

> You can reuse the same Spotify Developer app as MyDailyDrive if you like — the `.env` in this folder was seeded with those same credentials to get you started.

---

## Step 2 — Install Python dependencies

```bash
cd /Volumes/GDrive/Github/MyDailyNews

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Step 3 — Set up your credentials

```bash
cp .env.example .env
open -e .env
```

```
SPOTIPY_CLIENT_ID=abc123...
SPOTIPY_CLIENT_SECRET=xyz789...
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

> **Your `.env` file is listed in `.gitignore`** and will never be committed to GitHub.

---

## Step 4 — First run (authorize the app)

```bash
cd /Volumes/GDrive/Github/MyDailyNews
source .venv/bin/activate
python3 daily_news.py
```

A browser window opens asking you to log in to Spotify and authorize the app. After approving, the token is saved to `.cache` so future runs (including LaunchAgent) skip the browser step.

---

## Step 5 — Customise the playlist (optional)

Open `daily_news.py` and edit the **CONFIGURATION** block near the top:

| Variable | Default | What it does |
|---|---|---|
| `PRIORITY_PODCAST_IDS` | 4 Australian news shows | Spotify show IDs always included, always in order |
| `PLAYLIST_NAME` | `"My Daily News"` | Name of the Spotify playlist |

To add, remove, or reorder shows, edit `PRIORITY_PODCAST_IDS` and `PRIORITY_PODCAST_NAMES` at the top of `daily_news.py`.

---

## Step 6 — Schedule with LaunchAgent (runs automatically at 5 AM)

### 6a — Create the wrapper script

```bash
mkdir -p ~/.local/bin
```

Create `~/.local/bin/daily_news_run.sh`:

```bash
#!/bin/bash
# Wait up to 2 minutes for GDrive to mount
for i in $(seq 1 24); do
    if [ -d "/Volumes/GDrive/Github/MyDailyNews" ]; then
        break
    fi
    sleep 5
done

if [ ! -d "/Volumes/GDrive/Github/MyDailyNews" ]; then
    echo "$(date): GDrive not mounted after 2 minutes, aborting" >> /tmp/daily_news_error.log
    exit 1
fi

exec /Volumes/GDrive/Github/MyDailyNews/.venv/bin/python3 /Volumes/GDrive/Github/MyDailyNews/daily_news.py \
    >> /tmp/daily_news_output.log 2>&1
```

```bash
chmod +x ~/.local/bin/daily_news_run.sh
```

### 6b — Create the LaunchAgent plist

Create `~/Library/LaunchAgents/com.mahoney.dailynews.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.mahoney.dailynews</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/mahoney/.local/bin/daily_news_run.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>5</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>/tmp/daily_news_launchagent.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/daily_news_error.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

### 6c — Load the LaunchAgent

```bash
launchctl load ~/Library/LaunchAgents/com.mahoney.dailynews.plist
launchctl list | grep mahoney.dailynews
```

> **macOS approval:** installing a new LaunchAgent triggers a one-time notification asking you to allow background access. Go to **System Settings → General → Login Items & Extensions** and allow `com.mahoney.dailynews`.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `Missing required environment variables` | `.env` not set up | Follow Step 3 |
| `Authentication failed` | Wrong credentials or redirect URI | Double-check `.env` and the Spotify Dashboard redirect URI |
| `No episodes found for …` | Show ID changed or show is inactive | Find the new ID in the Spotify app and update `PRIORITY_PODCAST_IDS` |
| Script doesn't run at 5 AM | Mac was asleep | Set a scheduled wake with `pmset` |
| GDrive not mounted when script runs | Drive mounted after script fires | The wrapper script waits up to 2 minutes; check `/tmp/daily_news_error.log` |

---

## File structure

```
MyDailyNews/
├── daily_news.py       ← Main script
├── requirements.txt    ← Python dependencies
├── .env.example        ← Template for your credentials (safe to commit)
├── .env                ← Your actual credentials (never committed)
├── .gitignore          ← Excludes .env, .cache, logs, etc.
├── .cache              ← Spotipy auth token (auto-generated, never committed)
└── README.md           ← This file

~/.local/bin/
└── daily_news_run.sh   ← Wrapper script called by the LaunchAgent
```

---

## Finding a Spotify Show ID

1. Open Spotify and navigate to any podcast.
2. Click the three-dot menu → **Share** → **Copy link to show**.
3. The link looks like `https://open.spotify.com/show/1D4A4NKKF0axPvAS7h31Lu` — the ID is the last part.
