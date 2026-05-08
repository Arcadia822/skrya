# Default Digest Template

This template is writing and reference guidance for the agent producing a digest. Follow the structure and rules below unless a topic-specific digest template is configured.

## Structure

```markdown
# YYYY-MM-DD｜主题名｜每日简报

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
  - feedback: 调整简讯和事件线的获取策略，例如：`feedback: 6 7 我不喜欢，如果是 xxx 不要关注`。
```

## Rules

- Write every digest item as the same compact line box.
- Put the visible number and title on the first line.
- Put source references after one blank line inside the line box.
- Do not add a conversational preface before the title.
- Do not append saved-file notes after the system section.
- For English topics, use the same structure with English labels, `## System`, and the same `dig:` / `track:` / `feedback:` commands.
