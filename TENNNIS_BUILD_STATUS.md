# GOOL TENNIS build status

Implemented in this branch:

- Flashscore tennis LIVE discovery adapter.
- Flashscore tennis statistics adapter.
- 1xBet LIVE event matching adapter.
- Current-set winner and over-total probability engine.
- Early-set entry gate.
- Probability vs implied-market value filter.
- Telegram signal delivery through the existing second-bot subscriber store.
- Signal journal for one signal per match/set.
- Automatic SET WINNER result closure when the next set begins.
- Smoke tests for the probability core.

Next validation work before merging to main:

- Observe real Flashscore tennis feed rows and verify current-set/server field mapping for ATP, WTA, Challenger and ITF.
- Observe real 1xBet GetGameZip payloads and finalize semantic mapping for set winner and set total market nodes.
- Add exact SET TOTAL result closure using completed-set scores.
- Add Telegram daily analytics split by core, ATP/WTA, set number and line.
