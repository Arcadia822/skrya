# Event threads

Continuing stories ("threads") stay connected across days. A user can ask to see one thread's timeline by id or by a human name/alias, and Skrya rebuilds thread state from seeds and digest items.

## Sub-features

- `thread-view-id` renders a thread timeline by thread id.
- `thread-view-alias` resolves the thread by its display name or an alias.
- `thread-timeline-from-digest` shows timeline entries linked to digest item numbers (`关联日报：N`).
- `thread-refresh` rebuilds `runs/<topic>/threads/latest-threads.json`.
- `thread-missing` fails for an unknown thread, or when no thread artifact exists yet.

## How to get to it (user POV)

- User asks "比亚迪闪充站这条线现在怎么样" or replies `track: N ...` after a digest; the agent calls `thread` / `refresh-threads`.
- Operator runs `python3 -m skrya_orchestrator.main thread --root . --topic <id> --thread <id-or-name>`.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean.
- Topic `new-energy-vehicles` has seed thread `byd-flash-charge-station` (name `比亚迪闪充站`, aliases `BYD 闪充站`, `比亚迪兆瓦闪充站`).

- **Before any digest.** Run `$V skrya th-before -- thread --root . --topic new-energy-vehicles --thread byd-flash-charge-station`. Exit `1`; last stderr line `FileNotFoundError: Thread artifact not found for topic 'new-energy-vehicles'`.
- **Seed via digest.** Run `$V skrya digest -- digest --root . --topic new-energy-vehicles --sample`. Exit `0`.
- **View by id.** Run `$V skrya th-id -- thread --root . --topic new-energy-vehicles --thread byd-flash-charge-station`. Exit `0`; stdout starts `# 比亚迪闪充站`, has `**当前状态：** 持续跟进`, and `## 时间线` with entries ending `关联日报：1。` and `关联日报：2。`.
- **View by alias.** Run `$V skrya th-alias -- thread --root . --topic 新能源汽车 --thread "BYD 闪充站"`. Exit `0`; same heading `# 比亚迪闪充站`.
- **Refresh.** Run `$V skrya refresh -- refresh-threads --root . --topic new-energy-vehicles` and `$V snapshot after-refresh`. Stdout `Refreshed threads: <scratch>/data/runs/new-energy-vehicles/threads/latest-threads.json`; the snapshot contains that file.
- **Unknown thread.** Run `$V skrya th-nope -- thread --root . --topic new-energy-vehicles --thread nope`. Exit `1`; last stderr line `ValueError: Thread 'nope' not found for topic 'new-energy-vehicles'`.

## Gotchas

- `thread` needs `runs/<topic>/threads/latest-threads.json`, written by a real `digest` or `refresh-threads`; seeds alone are not enough.
- Only `new-energy-vehicles` has thread seeds among the fixtures.
- Thread names are Chinese; quote them in shell commands.
