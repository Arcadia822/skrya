# Default Digest Template

Use this template for every scheduled or user-requested real digest unless a topic-specific digest template is configured.

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
  - A. 详细分析指定今日简讯，例如：`A 3 5 12`。
  - B. 创建新的thread，例如：`B 3 4 5 持续关注`。
  - C. 调整简讯和thread的获取策略，例如：`C 6 7 我不喜欢，如果是 xxx 不要关注`。
```

## Rules

- Render every digest item as the same compact line box.
- Put the visible number and title on the first line.
- Put source references after one blank line inside the line box.
- Do not add a conversational preface before the title.
- Do not append saved-file notes after the system section.
- For English topics, use the same structure with English labels and `## System`.
