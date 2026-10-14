# Prompt 40 — Calibration (the learning loop)

Run monthly or after every 5 logged trips.

---

Review 7Fish forecasts against Matt's logged trips since {last calibration date}. Inputs: forecasts/{date} records, trips with their `rec` links, and the knowledge files those forecasts used.

1. Build a plain table: date, verdict, recommended play, what Matt actually did, outcome (target caught / other species / blank), and what the conditions really were.
2. Separate the causes of every miss: wrong conditions read, wrong knowledge (species band, spot access), bad data (gauge offline, stale report), or normal variance. A single blank is not evidence the fish left.
3. Propose specific edits to knowledge or gate files, each with the trips that support it and a confidence word. Firsthand access findings (crowding, casting room, flooding banks) are real evidence and can be adopted on one observation; biological claims need more than one trip.
4. Never propose a numeric score, and never tune toward recent luck.

Output: the table, the proposed diffs, and a two-line summary of what 7Fish is getting right and wrong. Nothing is committed until Matt approves.
