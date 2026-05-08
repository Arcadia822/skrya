# New Energy Thread Demo

Skrya can keep one developing story connected across days instead of treating each new item as an unrelated headline.

## User Request

```text
新能源汽车这个 topic 里，帮我持续跟比亚迪闪充站这条线。
```

## Thread Seed

```json
{
  "id": "byd-flash-charge-station",
  "name": "比亚迪闪充站",
  "status": "active",
  "summary": "围绕比亚迪闪充站建设、城市落地、合作扩张和实测反馈持续发展的 thread。",
  "watchpoints": [
    "首批站点在哪些城市真正落地",
    "配套车型和合作方是否同步跟进",
    "真实补能效率是否被媒体和车主反复验证"
  ]
}
```

## Follow-Up Behavior

```text
Day 1:
- digest item 2 mentions the first city list
- user replies: `track: 2 比亚迪闪充站`
- Skrya records a thread seed after confirmation

Day 5:
- a new charging-station update appears
- Skrya connects it to the existing thread
- the digest explains what changed since the last checkpoint
```

See also: [thread seed fixture](../docs/byd-flash-charge-thread-seed.example.json) and [thread timeline fixture](../docs/byd-flash-charge-thread.example.json).
