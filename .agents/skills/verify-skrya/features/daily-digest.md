# Daily digest

A user asks for today's briefing on a topic (or a scheduled automation runs it). Skrya renders a Chinese or English digest of numbered line-box items with sources, always shows active threads first under `## 事件线时间线更新`, ends with `## 系统提示` follow-up commands, and saves a timestamped artifact plus `latest-digest.md`. A test run renders the same body without saving anything.

## Sub-features

- `digest-real` renders a digest and writes `runs/<topic>/digest-YYYYMMDDTHHMMSS+0800.md`, `latest-digest.md`, and `latest-digest-events.json`.
- `digest-latest-pointer` repoints `latest-digest.md` to the newest artifact on each run.
- `digest-preview` (`--preview` / `--test-run`) renders identically but writes nothing.
- `digest-thread-section` shows every active thread, with either a verified increment or an explicit "本轮暂无可核验新增" review state.
- `digest-empty` refuses to pass sample data off as real when live sources produced nothing.
- `digest-topic-by-name` accepts the topic's display name instead of its id.
- `digest-unknown-topic` fails clearly for a topic that does not exist.

## How to get to it (user POV)

- User says "给我今日简报" / "跑一次日报" / asks for a test run in an agent with Skrya installed; the `digest` skill calls `digest --topic <id>` (or `--preview` for a test run).
- Scheduled automation prompt runs the same `digest` command.
- Operator runs `python3 -m skrya_orchestrator.main digest --root . --topic <id>` directly.

## Driving it with verify-skrya

Preconditions:

- Fresh run launched and `$V doctor` clean.
- No `runs/new-energy-vehicles/` yet.

- **Preview writes nothing.** Run `$V skrya preview -- digest --root . --topic new-energy-vehicles --sample --preview` then `$V snapshot after-preview`. Exit `0`; stdout starts with `# <YYYY-MM-DD>｜新能源汽车｜每日简报`; the snapshot contains `runs-absent.txt` (no `runs/` created).
- **Real digest.** Run `$V skrya digest -- digest --root . --topic new-energy-vehicles --sample`. Exit `0`; stdout has, in order: `## 事件线时间线更新` with `┌─ **【Thread】比亚迪闪充站 (byd-flash-charge-station)**`, `## 今日简讯`, `【简讯1】`…`【简讯3】` each with a `│ 信源：` line, `---`, `## 系统提示` listing `dig:` and `track:` follow-ups.
- **Artifacts written.** Run `$V snapshot after-digest`. `runs/new-energy-vehicles/` contains exactly one `digest-*+0800.md` whose content equals the step's `stdout.txt`, `latest-digest.md` as a symlink to it (see `tree.txt`), `latest-digest-events.json` with `items[].number` 1..3, and `threads/latest-threads.json`.
- **Pointer moves.** Wait ≥1 s, run `$V skrya digest-again -- digest --root . --topic 新能源汽车 --sample` and `$V snapshot after-second`. Two `digest-*.md` files exist and `latest-digest.md ->` names the newer one. This also proves `digest-topic-by-name`.
- **Thread with no increment.** Run `$V skrya live-empty -- digest --root . --topic new-energy-vehicles --preview` (no `--sample`, no ingest). The thread box still appears with `复核结果：已检查，本轮暂无可核验新增。`, followed by `暂时没有抓到足够新的真实内容，先不拿样例数据冒充日报。`.
- **Empty topic without threads.** Run `$V skrya agi-empty -- digest --root . --topic agi-news --preview`. Stdout has the title, the same "暂时没有抓到足够新的真实内容" line, and no `## 事件线时间线更新`.
- **Unknown topic.** Run `$V skrya unknown -- digest --root . --topic nope --preview`. Exit `1`; last stderr line `FileNotFoundError: Topic 'nope' not found`.

## Gotchas

- Artifact names have 1-second resolution; two real digests in the same second overwrite each other. Space them out when proving the pointer.
- Without `--sample`, `k-entertainment` fetches five live RSS feeds and the output depends on the network; use `--sample` for deterministic proof and say so.
- Every digest runs `git ls-remote origin main` for the version-check line; offline runs just omit that line.
- `Agent：` / `LLM：` lines in `## 系统提示` come from host env vars; do not assert on them.
- A preview does not refresh `latest-digest-events.json`, so `dig: N` after a preview still resolves against the last real digest.
