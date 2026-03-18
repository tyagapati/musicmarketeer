# API Keys Setup Guide

This document explains what API keys you need and where to get them.

## Required: None! 🎉

The app works **without any API keys** for basic functionality:
- ✅ Campaign builder form
- ✅ Matching engine
- ✅ Admin dashboard
- ✅ Manual marketer entry
- ✅ All core features

## Optional: Reddit API (for RedditConnector)

**Only needed if you want to automatically discover marketers from Reddit.**

### Why Reddit API?
The RedditConnector searches Reddit posts/comments for music marketers. It uses the official Reddit API (no scraping, fully compliant).

### How to Get Reddit API Credentials:

1. **Go to Reddit Apps**: https://www.reddit.com/prefs/apps
   - You need to be logged into Reddit

2. **Create a New App**:
   - Scroll down and click **"create app"** or **"create another app"**
   - Fill in:
     - **Name**: `SoundMatch MVP` (or any name)
     - **App type**: Select **"script"**
     - **Description**: Optional
     - **About URL**: Optional (can be `http://localhost`)
     - **Redirect URI**: `http://localhost` (required, but not used for script type)

3. **Get Your Credentials**:
   - After creating, you'll see your app listed
   - **Client ID**: The string under your app name (looks like: `abc123def456ghi`)
   - **Client Secret**: The "secret" field (looks like: `xyz789_secret_key_here`)

4. **Update .env**:
   ```env
   REDDIT_CLIENT_ID=your_client_id_here
   REDDIT_CLIENT_SECRET=your_client_secret_here
   REDDIT_USER_AGENT=soundmatch-mvp/1.0 by /u/yourredditusername
   ```
   - Replace `yourredditusername` with your actual Reddit username

### What the RedditConnector Does:
- Searches subreddits: `musicmarketing`, `WeAreTheMusicMakers`, `indieheads`, `makinghiphop`, `musicbusiness`
- Looks for posts/comments mentioning music marketing services
- Extracts contact info, services, and genres
- Creates pending marketer entries for admin review

### Without Reddit API:
- The app works perfectly fine
- You can manually add marketers via the admin panel
- You can use the WebDirectoryConnector for other sources
- Ingestion jobs will skip Reddit if credentials aren't set

## Optional: Redis (for Background Jobs)

**Only needed if you want async background processing for ingestion jobs.**

### Why Redis?
RQ (Redis Queue) uses Redis to run background jobs. Without it, ingestion runs synchronously (still works, just blocks the request).

### How to Get Redis:

**Option 1: Local Installation**
- **Windows**: Download from https://github.com/microsoftarchive/redis/releases or use WSL
- **Mac**: `brew install redis` then `brew services start redis`
- **Linux**: `sudo apt-get install redis-server` then `sudo systemctl start redis`

**Option 2: Cloud Redis (Production)**
- Redis Cloud: https://redis.com/try-free/
- AWS ElastiCache
- Azure Cache for Redis

**Option 3: Skip It**
- The app works without Redis
- Ingestion jobs run synchronously (immediate response)
- No background worker needed

### Update .env**:
```env
REDIS_URL=redis://localhost:6379/0
```

## Summary

| Service | Required? | Purpose | Where to Get |
|---------|-----------|---------|--------------|
| **Reddit API** | ❌ Optional | Auto-discover marketers from Reddit | https://www.reddit.com/prefs/apps |
| **Redis** | ❌ Optional | Background job processing | Local install or cloud service |
| **Database** | ✅ Required | But SQLite works out of the box | None needed (SQLite) |

**Bottom line**: You can start using the app immediately with just the `.env` file as-is. Add API keys later if you want those features!


