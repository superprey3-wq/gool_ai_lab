# GOOL AI LAB

Experimental AI-first fork of GOOL.

This repository runs independently from the production `gool_bot`. At startup it clones a pinned production baseline, then loads an AI-first controller where Gemini makes the final ENTER/WATCH/REJECT decision while GOOL metrics remain input features.

Required environment variables:
- `TELEGRAM_BOT_TOKEN` — second Telegram bot token
- `TELEGRAM_CHAT_ID` — owner/chat id if used by the base bot
- `GEMINI_API_KEY` — Gemini API key

Optional:
- `GEMINI_MODEL` (default `gemini-2.5-flash`)
- `AI_FIRST_MIN_PROB` (default `65`)
- `AI_FIRST_FAIL_OPEN` (default `0`)
- `GOOL_BASE_REF` (default pinned baseline commit)

Start command: `python main.py`
