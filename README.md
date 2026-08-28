# GOOL MARKET AI

Independent football market-intelligence Telegram bot for the MonkeyBytes node.

## Goal

Collect repeated live odds snapshots, normalize markets/bookmakers, measure market movement, and send only high-confidence market-flow alerts to the already connected Telegram bot.

## Architecture

- Playwright/Chromium browser collector (optional/fallback-capable)
- pluggable collectors: OddsPortal/OddsHarvester-compatible and Flashscore-compatible
- SQLite snapshot history
- MOVE / VELOCITY / BREADTH / PERSISTENCE / REVERSAL scoring
- no-vig fair probability and value calculations
- one active alert per event/market direction with cooldown
- Telegram delivery using TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
- resource guard and periodic browser restart for small 24/7 hosts

## Start

```bash
pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

On hosts where Chromium system dependencies are already present this is enough. If the host allows OS package installation, Playwright also supports installing Chromium dependencies with `python -m playwright install --with-deps chromium`.

## Safety

The bot does not place bets. It produces market-analysis alerts. Data collectors are isolated so a source failure does not stop the scoring/runtime loop.
