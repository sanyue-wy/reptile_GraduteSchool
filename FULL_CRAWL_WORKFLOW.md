# 全量采集工作流指南

## 概述

本项目支持从单校采集扩展到全量采集（100+ 所双一流高校）。完整工作流分为三个阶段：

1. **URL 发现** - 自动搜索各学校师资列表页真实 URL
2. **人工审核** - 确认候选 URL 并配置 CSS 选择器
3. **全量采集** - 并发爬取所有已配置学校

---

## 第一阶段：URL 自动发现

### 运行批量发现

```bash
# 发现所有学校（建议分批次运行，避免搜索引擎限制）
python scripts/batch_discover_urls.py

# 仅发现特定学校
python scripts/batch_discover_urls.py --schools "东南大学,北京大学,清华大学"

# 仅发现特定学科
python scripts/batch_discover_urls.py --categories "mechanical"
```

### 输出结果

候选结果保存在 `data/candidates/` 目录下，每个文件格式：

```json
{
  "university": "东南大学",
  "college": "机械工程学院",
  "discovered_at": "2026-09-16T18:47:39.177572",
  "candidates": [
    {
      "url": "https://me.seu.edu.cn/szdw/list.htm",
      "score": 8.5,
      "list_type": "static_html",
      "source": "search_duckduckgo",
      "title": "师资队伍 - 东南大学机械工程学院",
      "markers": ["teacher_card:教授", "path:szdw", "title_match"],
      "reachable": true,
      "status_code": 200
    }
  ],
  "summary": {
    "total": 5,
    "reachable": 3,
    "top_score": 8.5
  }
}
```

---

## 第二阶段：人工审核与配置

### 交互式审核

```bash
# 交互式审核所有候选
python scripts/review_candidates.py

# 仅查看特定学校
python scripts/review_candidates.py --school "东南大学"

# 自动选择最高分候选（需配合 --apply）
python scripts/review_candidates.py --auto-approve --apply
```

### 审核要点

1. **确认 URL 正确性** - 打开浏览器验证是否为目标学院师资页
2. **选择 list_type** - `static_html` / `ajax_api` / `js_render` / `pdf_list`
3. **配置 CSS 选择器** (static_html 类型必须)：
   - `list_item_selector`: 教师条目容器选择器（如 `li.teacher-item`）
   - `list_name_selector`: 姓名选择器（如 `a.title` 或 `title` 属性）
   - `list_research_selector`: 研究方向选择器（可选）

### 示例配置

```json
{
  "faculty": {
    "enabled": true,
    "list_type": "static_html",
    "list_url": "https://me.seu.edu.cn/szdw/list.htm",
    "list_item_selector": "li[style*='display']",
    "list_name_selector": "a[title]",
    "list_research_selector": ".research",
    "detail_selectors": {
      "name": ".name",
      "title": ".title",
      "research": ".research",
      "email": ".email",
      "phone": ".phone"
    }
  }
}
```

---

## 第三阶段：全量采集

### 启动采集

```bash
# 全量采集（断点续抓）
python scripts/crawl_all.py --resume

# 首次全量采集
python scripts/crawl_all.py --year 2026 --workers 4

# 仅采集 Source A
python scripts/crawl_all.py --source source_a

# 仅采集机械类
python scripts/crawl_all.py --category mechanical

# 重试失败项
python scripts/crawl_all.py --retry-failed
```

### 并发控制建议

| 场景 | workers | delay_range | 说明 |
|------|---------|-------------|------|
| 首次采集 | 2-4 | 2-5s | 保守策略，避免触发反爬 |
| 断点续抓 | 4-8 | 1-3s | 已有缓存，速度可快些 |
| 重试失败 | 1-2 | 5-10s | 针对性重试，延迟更大 |

### 监控进度

- 实时日志：`data/output/crawl.log`
- 进度状态：`data/output/progress.json`
- 失败记录：`data/output/failures.json`

---

## 常用命令速查

```bash
# 1. 发现 URL（分批次，每次 10-20 所学校）
python scripts/batch_discover_urls.py --schools "学校1,学校2,..."

# 2. 审核并应用配置
python scripts/review_candidates.py --school "学校1" --apply

# 3. 启动采集
python scripts/crawl_all.py --resume --workers 4

# 4. 查看进度
tail -f data/output/crawl.log

# 5. 导出汇总表（采集完成后自动生成）
# data/output/summary.xlsx
```

---

## 注意事项

1. **搜索引擎限制** - 批量发现时建议 `workers=1`，延迟设大些
2. **反爬策略** - 系统内置熔断器、冷却机制，遇到 403 自动等待
3. **断点续抓** - 使用 `--resume` 自动跳过已完成任务
4. **缓存机制** - 默认缓存 7 天，二次采集极快，用 `--no-cache` 强制刷新
5. **配置验证** - 修改配置后会自动校验必填字段

---

## 目录结构

```
reptile_GraduteSchool/
├── config/
│   ├── school_data.json      # 学校配置（含 URL、选择器）
│   └── school_level_raw.py   # 学校层次定义
├── data/
│   ├── candidates/           # URL 发现候选结果
│   ├── raw/                  # 原始页面缓存
│   └── output/               # 采集结果、日志、进度
├── scripts/
│   ├── batch_discover_urls.py   # 批量 URL 发现
│   ├── review_candidates.py     # 候选审核与配置更新
│   └── crawl_all.py             # 全量采集启动
├── main.py                   # 主入口（支持 --school __all__）
└── spiders/
    └── url_resolver.py       # URL 自动发现核心逻辑
```