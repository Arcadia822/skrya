# Default digest template

Use this writing contract unless a confirmed topic template overrides it. Plain Markdown is the complete archive. Native channel rendering is a separate step.

Native news date badges show `MM-DD HH:mm` when a recorded time exists, or `MM-DD` for date-only sources. Never invent a time. Preserve complete dates in archives and historical milestones. Module headings use the approved centered symmetric decoration `✦ ─── … ─── ✦`.

Keep each Thread's latest developments and historical timeline in one yellow block under one T-xx heading. Split only when the serialized request or component budget requires it; repeat the Thread heading only on actual continuation blocks.

## Structure

```markdown
# YYYY-MM-DD｜主题名｜每日简报

扫描时间范围：真实起止时间与时区。

## 事件线时间线更新

### T-01 事件线名称

**最新进展**：
- **YYYY-MM-DD HH:mm** · [真实新闻标题](https://example.com/news) · N-01
一句事实简介，保留关键主体、行动和数据。
点评：简明解释影响，不重复事实。

**历史时间线**：
- [起因或正式决定](https://example.com/origin) ｜ YYYY-MM-DD
- [重大转折或阶段结果](https://example.com/result) ｜ YYYY-MM-DD

无新增时写明：本轮暂无可核验新增。
最新状态：真实日期、最近已知状态及下一步观察。
未完成策展时写明：尚无已核定日期的重要节点，全量报道档案仍保留。

## 今日简讯

### N-01 事件标题 ｜ YYYY-MM-DD HH:mm
事实简介，约三行以内。上游写作保持精炼，渲染器不得截断已有事实。
为何重要：约两行以内的判断。
信源：[媒体A](https://example.com/a) | [媒体B](https://example.com/b)

---

## 可继续操作

- 回复 `dig: N-01`，展开指定新闻的深度分析与专家级背景研判。
- 回复 `track: N-02`，为指定事件建立持续追踪线。
- 回复 `dig: T-01`，查看事件线的全量历史脉络。
- 回复 `write: T-01`，把这一系列事件写成有来源的文章草稿，不自动发布。
- 自然语言反馈，例如增加涉华舆情分析或减少例行口水争端。
```

## Rules

- Use uniform Markdown entries, never ASCII line boxes, decorative border characters or tabs for alignment.
- Include the Thread section before news whenever an effective thread has `status=active`. Every active thread remains visible even with no verified update. Omit the section only when there are no active threads.
- Latest developments show every verified news item separately with its real date, title link, facts and comment. Retain linked N-xx references. Do not turn multiple news items into a synopsis.
- The raw `timeline` retains all reporting from the Thread's inception. Append and deduplicate without discarding unknown fields, old reports or sources. Dig and write read the complete archive, not the display projection.
- Historical timeline display selects causes, formal decisions or actions, major turning points and stage results across the complete lifetime. Do not choose the latest N entries or infer importance from keywords.
- An editorially selected entry has a concrete `milestone_reason`, optionally `milestone_title`. Display requires a valid source URL and a genuine event date. A recovered `milestone_date` also records `milestone_date_basis`. Unknown dates remain in the archive, not the display timeline. Never substitute collection dates.
- Current-year display dates may use MM-DD. Cross-year dates include YYYY-MM-DD. Show HH:mm only if recorded. Never truncate an RFC date string to make a badge.
- Visible N-xx and T-xx numbers refer to the immutable digest snapshot. Keep internal Thread IDs out of user titles. Resolve received-card actions against that card's delivered snapshot, not a newer generated digest.
- Link media names directly. Separate sources with ` | `. Do not label links with the redundant text 原文链接.
- Native Feishu cards use Schema 2.0, a blue header, orange T badges, blue N badges, separate yellow-50 Thread blocks, blue-50 news blocks and a grey actions block. Use native centered section headings, column padding 14px 18px, title left and date badge right. Keep facts and grey commentary in separate paragraphs.
- Keep exactly the five actions shown above. Do not add model, version, execution log, credential details or delivery conclusions to the footer. Store execution and delivery status in run artifacts.
- Test previews use this same contract but do not create formal artifacts or update latest pointers. Never fabricate current news from sample data.
- English topics use the same contract with Event Timeline Updates, Latest developments, Historical timeline, Latest known state, Sources, Available actions and Natural-language feedback. Supported topic languages remain Chinese and English.
