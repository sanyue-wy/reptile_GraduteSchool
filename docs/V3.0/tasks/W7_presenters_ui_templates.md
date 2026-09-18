# W7 任务卡：呈现器 / UI 组件 / 20 套模板 / 控制台

## 角色

呈现与前端开发者。交付五个内置呈现器、四个 HTML UI 组件、20 套完整模板 + ThemeSwitcher，以及控制台三功能页面（插件管理/任务定义/输出定义）。成品报告属于本窗口，不属于控制台实现。

## 必读（只读这些）

- [README.md](README.md)
- `docs/V3.0/INTERFACES.md`（重点：PresentationRequest/RenderedOutputDTO/ViewModel/UIComponentDTO、PresenterPlugin 协议（execute 为唯一抽象入口）、UIPlugin 协议、renderer manifest、API 端点表 §8.2）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §3（存储与呈现边界）、§8
- 现状代码：dashboard/（现有 Flask 页面：总览/学校/导师/失败/配置五页，保留不动）、api/server.py 现有端点（兼容面）、utils/progress.py 读取接口（展示状态用）

## 可写范围（独占）

```text
plugins/presenters/**              # base_presenter.py + html/text/jsonl/csv/pdf 五个包
plugins/ui/**                      # table_component/ chart_component/ card_component/ filter_component/
templates/**                       # registry.json + 20 套目录
dashboard/console/**               # index.html(三功能导航) plugins.html task-config.html output-config.html
dashboard/runtime/**               # 成品授权预览/静态服务桥（不保存配置逻辑）
tests/test_presentation_plugins.py
tests/test_ui_plugins.py
tests/fixtures/presentation/**
```

**禁止修改**：dashboard/ 下现有五页及其 API 依赖（旧 presenter kind 的页面保留，你的 console 是新增目录）、contracts/、pipeline/、api/server.py（新端点由 W2 写：GET /api/ui/components、PUT /api/ui/components/layout；你提供后端数据函数并在 INTERFACES.md 登记）、其他 plugins 子目录。

## 交付清单

### A. 五个呈现器（plugins/presenters/，plugin_type=presenter，均实现 PresenterPlugin.execute(PresentationRequest, context) → RenderedOutputDTO）

1. **html_presenter**：经受管 UI resolver 组合 UI 组件描述 → 套用 templates/ 中指定模板 → 产出**可独立打开**的 HTML 成品包（内联或相对路径引用样式/脚本/媒体，双击文件即可看，不依赖运行中的 API）。含 theme_switcher.py：在成品内切换主题（纯前端 JS，无网络请求）。
2. **text_presenter**：两种模式 params.mode = "text" | "markdown"。
3. **jsonl_presenter**：面向交换的 JSONL 成品（可与 W6 jsonl_store 共享序列化器，写 runs outputs 命名空间）。
4. **csv_presenter**：列集来自 OutputSpec 字段选择。
5. **pdf_presenter**：可选依赖（如 weasyprint/reportlab，选型后走 progress.md 登记并核 LICENSE）；无依赖时预检报缺失，测试显式 skip 单列。XML 只是扩展格式规范，**不做第六个内置实现**。

所有呈现器：不重新抓取、不重复存储、不直接导入其他插件私有实现；输出到 data/runs/<run_id>/outputs/<output_id>/；RenderedOutputDTO.media_assets 携带随附媒体引用。

### B. 四个 UI 组件（plugins/ui/，plugin_type=ui，UIPlugin: ViewModel → UIComponentDTO）

table / chart(Chart.js) / card / filter 各一个插件包：声明式 payload schema（metadata.config_schema 收紧）、renderer manifest（版本/同源资源/payload schema/能力）。宿主通用注册入口 registerRenderer(id, impl) 风格——**不能用四个硬编码 renderer 冒充开放 UI 插件**；未知 renderer 显示占位+诊断。filter 事件只传动作 ID + 经校验参数：查询过滤走授权查询接口；仅明确的"开始采集"动作才触发 request_converter 建任务；普通筛选绝不触发重抓。HTML 文本安全插入 + CSP，不接收任意脚本 URL/事件代码。

### C. 20 套模板（templates/）

每套目录四件齐全：layout.html / style.css / variables.json（变量声明）/ preview.png（可用脚本生成占位图但必须存在且尺寸一致）。registry.json 登记 name/description/theme(light|dark|both)/variables 映射/preview 路径/版本。首套 minimal-light 作为验收基准模板，其余 19 套覆盖学术/极简/深色/卡片流等方向（命名自定但 registry 全量列出）。模板只做布局与变量声明：不含爬虫逻辑、业务合并、控制台 API 调用。

### D. 控制台三功能（dashboard/console/）

- index.html：仅三个入口的导航（插件管理/任务定义/输出定义），不复制旧五页。
- plugins.html：调 GET /api/plugins（W3 治理视图）展示批准状态/版本/启停操作。
- task-config.html：任务定义表单（对接 schema_editor 产出的 FormSpec，W8 交付编辑器本体，你先用其接口契约 stub）。
- output-config.html：输出定义（presenter 实例 + 模板选择 + 字段选择 → OutputSpec；"从已有记录重新呈现"按钮调 W2 端点，不重新抓取）。
- runtime/：成品授权预览桥——token 化临时链接访问 runs outputs，只读，不落配置。

## 验收命令

```bash
python -m pytest tests/test_presentation_plugins.py tests/test_ui_plugins.py -q
python -c "import json; r=json.load(open('templates/registry.json',encoding='utf-8')); print(len(r['templates']))"   # == 20
```

浏览器验收（Playwright，启动临时 Flask 实例 + fixture 数据，参考 V2.2 offline_preview 做法）：
- 四组件渲染正确、过滤交互、分页、刷新、未知类型占位；全程 pageerror 为空。
- HTML 成品包在 file:// 下独立打开可看（截图留档）。
- 控制台三页可达、输出定义保存后 revision 递增。
- 注入用例：payload 含 `<script>` 文本被转义，无任意 HTML 注入。

## 特别注意

- 大数据集不把整份数据嵌进页面：运行描述存受管输出路径，前端经授权 API 分页读取（这是 hosted 预览模式）；file:// 独立成品模式允许内联数据，两种模式在 INTERFACES.md 明确区分（走仲裁登记）。
- 第三方 JS（Chart.js 等）须管理员批准流程（W3 的资源批准机制），版本锁定进 manifest。
- 覆盖率 ≥80%（Python 侧）；前端以浏览器用例为准，不追求 JS 单测覆盖率指标。
