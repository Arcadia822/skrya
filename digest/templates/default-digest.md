# Default Digest Template

This template is writing and reference guidance for the agent producing a digest. Follow the structure and rules below unless a topic-specific digest template is configured.

## Structure

```markdown
# YYYY-MM-DD｜主题名｜每日简报

## 事件线时间线更新

┌─ **【Thread】事件线名称 (thread-id)**
│ 今日增量：本轮可核验的新进展。
│ 时间线位置：承接 YYYY-MM-DD 的最近状态。
│ 影响判断：这次推进改变了什么。
│
│ 下一步观察：后续需要复核的信号。
└

无可核验新增时，同一模块改为：

┌─ **【Thread】事件线名称 (thread-id)**
│ 复核结果：已检查，本轮暂无可核验新增。
│ 最新状态：YYYY-MM-DD：最近时间线标题与简要状态。
│
│ 下一步观察：后续需要复核的信号。
└

┌─ **【简讯1】事件标题**
│ 一句判断或摘要。
│ 可以继续换行补充判断。
│
│ 信源：[来源名](url) [来源名](url)
└

---

## 系统提示

- 执行时间：YYYY-MM-DD HH:MM（Asia/Shanghai）
- 执行状态：完成/未抓到足够新的真实内容。
- 扫描时间范围：最近 24 小时或本轮 ingest 范围。
- Skrya：版本号
- 可继续操作：
  - dig: 详细分析指定今日简讯，例如：`dig: 3 5 12`。
  - track: 创建或更新持续事件线，例如：`track: 3 4 5 持续关注`。
  - 偏好反馈：直接用自然语言回复，例如：`低质量传闻少推`。
```

## Rules

- Write every digest item as the same compact line box.
- When any effective thread has `status=active`, always include `## 事件线时间线更新` before the normal digest items. Use `## Event Timeline Updates` for English topics.
- Give every active thread its own line box with the thread name and ID, today's increment, timeline position, impact judgment, and next observation.
- If the current scan finds no verified increment for an active thread, keep the line box, state `复核结果：已检查，本轮暂无可核验新增。`, and show the latest known timeline date, headline, and concise summary before the next observation.
- Do not show the event-timeline section when there is no active thread.
- Put the visible number and title on the first line.
- Put source references after one blank line inside the line box.
- Do not add a conversational preface before the title.
- Do not append saved-file notes after the system section.
- For English topics, use the same structure with English labels, `## System`, and `dig:` / `track:` commands plus plain-language preference feedback.
