# Algorithm Mirror

Shows people what their social feeds put in front of them, and how that compares to what they actually engage with.

A Chrome extension records what YouTube, Reddit, X, and LinkedIn show you, and syncs your likes, saves, and watch history (including from your phone). TikTok and Instagram data comes from export uploads. An AI model labels every post by topic and tone, and each participant gets a private dashboard.

**Full walkthrough: [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)**

## Repo layout

| Folder | What's in it |
|---|---|
| `extension/` | The Chrome extension |
| `server/` | FastAPI server, database setup, labeling scripts |
| `dashboard/` | The participant dashboard and upload page |
| `docs/` | Documentation |

## Stack

Chrome extension (JavaScript) · Python + FastAPI · PostgreSQL · Llama 3.1 8B via Ollama · DigitalOcean + Caddy

INFO 4700 Senior Capstone, CU Boulder