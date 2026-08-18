# GOOL TENNIS

Independent tennis conversion of the second GOOL Telegram bot. Production `gool_bot` is not modified.

## Data flow

- Flashscore tennis LIVE feed: matches, set/game state and live match statistics.
- 1xBet LiveFeed: current tennis markets and prices.
- GOOL TENNIS probability core: evaluates only the current set.
- Telegram: sends one strongest early-set signal per match/set.

## Signal models

### SET WINNER CORE
Predicts Player 1 or Player 2 to win the current set. The model estimates each player's probability of holding serve from live serve statistics and solves the remaining set as a probability tree.

### SET TOTAL CORE
Predicts over-games totals for the current set. The same probability tree produces the distribution of possible final set lengths, then GOOL compares its probability with the live 1xBet price.

## Entry gate

Default entry window is after 2 to 5 games have appeared in the set. A signal is sent only when:

- model probability is at least 67%;
- 1xBet odds are between 1.35 and 2.60;
- GOOL probability exceeds the market implied probability by at least 5.5 percentage points;
- there has not already been a signal for this match/set.

All thresholds are configurable through environment variables.

## Required environment

- `TELEGRAM_BOT_TOKEN` — token of the second Telegram bot.
- `TELEGRAM_CHAT_ID` — owner/chat id if used by the shared subscriber helper.

See `.env.example` for GOOL TENNIS and 1xBet settings.

## Start

```bash
python main.py
```

The repository still clones a pinned production GOOL baseline at startup, but only to reuse the proven Flashscore transport and Telegram subscriber helper. Football decision logic, Gemini football scouting and goal watching are not started by the tennis runtime.
