# GitHub 同类工程调研报告

> 调研日期：2026-09-14｜关键词：高校导师 爬虫 / 研招网 / 双一流 / 导师名单

---

## 一、按借鉴价值排序的仓库清单

### ⭐⭐⭐ 最高价值（直接可用资产）

#### 1. `freecho/yzw` — 研招网硕士招生目录爬虫
- **链接**：https://github.com/freecho/yzw
- **Stars**：37｜**语言**：Python｜**最近更新**：2026-04-01（**活跃维护**）
- **覆盖范围**：研招网（yz.chsi.com.cn）全国所有院校硕士专业目录
- **抓取目标**：每校每专业的**指导教师（zdjs）、招生人数、研究方向、考试科目、学位类型、学习方式、院系**
- **技术栈**：`aiohttp` 异步爬虫 + `BeautifulSoup4` + `SQLAlchemy` + `PyMySQL` + `fake-useragent` + 代理管理器
- **架构亮点**：
  - `data/school_level.py`：**完整985/211/双一流高校名单**（39所985 + 116所211 + 147所双一流）→ **可直接复制到我们的 config/schools.py**
  - `data/entity.py`：统一的 `Major` 数据模型（字段名直接对齐研招网 API 返回值）
  - `crawler/crawler.py`：异步抓取逻辑（含断点续抓 `breakpoint`、随机延时 0.8~1.2 倍率、失败日志、代理切换）
  - `crawler/login.py`：研招网 CAS 登录流程（cookie 管理，部分页面需登录）
  - `data/db.py`：入库逻辑（含 `get_school_level()` 自动打标签）
  - `proxy_manager.py`：代理池管理
- **可直接借鉴**：
  1. **学校名单**：`school_level.py` 的985/211/双一流集合——我们项目147所学校的配置表骨架，省掉手动整理工作量
  2. **研招网 API 对接**：研招网的 `zsml/rs/dws.do` 接口结构（form 参数 `dwmc/dwdm/xxfs/tydxs/jsggjh/start/pageSize`），`freecho/yzw` 已逆向并封装好
  3. **限速与反爬策略**：随机延时、代理切换、失败日志、断点续抓——我们 DESIGN.md 中 `utils/http.py` 的设计参考
  4. **导师字段提取**：研招网专业目录返回的 `zdjs`（指导教师）字段直接对应我们的"导师招生情况"需求
- **注意点**：研招网部分页面需要 CAS 登录（已有 login.py），需准备账号；爬的是"招生专业目录"而非"招生导师公示名单"——前者数据更丰富（含导师+名额+方向），覆盖面比公示名单更广

---

#### 2. `xx025/yanx` + `xx025/yzw-dl` — 研招网目录下载 GUI 工具
- **链接**：https://github.com/xx025/yanx （GUI 前端）｜https://github.com/xx025/yzw-dl （核心库）
- **Stars**：yanx 228 / yzw-dl 待确认｜**语言**：JavaScript + Python｜**最近更新**：2023-12
- **覆盖范围**：研招网全国所有院校硕士专业目录（与 freecho/yzw 同源目标）
- **技术栈**：FastAPI（后端） + webview（桌面 GUI） + yzw-dl（核心爬取库）
- **功能**：支持按学位类别（学硕/专硕）、门类、学科、全日制/非全日制、**985/211/双一流**、A/B区等维度筛选下载，导出 CSV
- **可直接借鉴**：
  1. **研招网院校库 CSV**（`assets/院校库.csv`）：来自研招网官方院校库的全国院校列表——现成的学校基础信息数据
  2. **A/B区与985/211对照表**（`assets/AB类地区和985、211院校目录`）：现成的分类映射数据
  3. **研招网 API 逆向细节**：yzw-dl 库对研招网各接口的完整参数封装，比 freecho/yzw 更细致
- **注意点**：最后更新 2023 年底，研招网接口可能有变动，需实测验证

---

### ⭐⭐ 中等价值（架构参考 + 延伸数据源）

#### 3. `Hthing/yzw` — Scrapy 版研招网爬虫
- **链接**：https://github.com/Hthing/yzw
- **Stars**：69｜**语言**：Python｜**最近更新**：2024-10
- **技术栈**：Scrapy 框架
- **可借鉴**：Scrapy pipeline 设计（Item Loader、去重、导出），若未来改用 Scrapy 重写可参考；Scrapy 的 Middlewares 对 UA 池和代理的处理比手写更成熟
- **不采用原因**：我们已决定不用 Scrapy，但其 `items.py` 中的字段定义（对应研招网字段）值得对照校验完整性

#### 4. `zengkaipeng/CSLabInfo2022` — CS 保研导师招生广告汇总（人工众包）
- **链接**：https://github.com/zengkaipeng/CSLabInfo2022
- **Stars**：275｜**最近更新**：2023-09
- **形式**：每个导师一个 Markdown 文件（如 `清华大学-许华哲老师.md`），包含研究方向、报名流程、联系方式
- **覆盖**：CS 方向为主，约16位导师（人工投稿），非系统性采集
- **可借鉴**：
  1. **数据结构模板**：其 Markdown 中的字段组织（教师介绍→研究方向→报名流程→广告提供者）可作为我们"导师详情"输出格式的参考
  2. **延伸价值**：如果未来想叠加"导师评价/口碑"数据，`KeGong-XKK/advisor-eval`（7.5万条导师评价，2026年活跃）是现成的评价数据源

#### 5. `cocos56/Graduate_admissions_data_analysis_tool` — 考研大数据分析
- **链接**：https://github.com/cocos56/Graduate_admissions_data_analysis_tool
- **Stars**：42｜**语言**：Python｜**最近更新**：2020-07（较旧）
- **可借鉴**：数据清洗和分析维度的思路（如何对研招网原始数据做去重、按学校/专业/省份聚合）
- **不采用原因**：代码较旧，接口可能失效

---

### ⭐ 辅助参考

#### 6. `KeGong-XKK/advisor-eval` — 导师匿名口碑查询 Skill
- **链接**：https://github.com/KeGong-XKK/advisor-eval
- **Stars**：2｜**最近更新**：2026-09-02（**非常新**）
- **内容**：约7.5万条研究生导师评价数据，支持按方向筛选导师，Claude Code Skill 格式
- **延伸价值**：未来若想在爬虫基础上叠加"导师口碑"维度，这是现成数据源

#### 7. `librauee/Reptile` (★1752) — Python3 爬虫实战合集
- **可借鉴**：其中有研招网爬虫示例代码，可作为入门参考
- **不采用原因**：综合性教学仓库，非专门针对本项目

---

## 二、我们项目应从这些仓库"抄"什么

### 立即可用（不写代码直接拿）
| 资产 | 来源 | 用途 |
|---|---|---|
| 985/211/双一流高校完整名单（147所） | `freecho/yzw` → `data/school_level.py` | 填充我们 `config/schools.py` 的学校列表骨架，省掉手动整理 |
| 研招网院校库 CSV | `xx025/yanx` → `assets/院校库.csv` | 补充学校基础信息（省份、代码等） |
| A/B区 + 985/211 对照表 | `xx025/yanx` → `assets/AB类地区和985、211院校目录` | 学校分类映射数据 |

### 架构思路借鉴
| 模块 | 参考源 | 我们怎么用 |
|---|---|---|
| **研招网 API 对接** | `freecho/yzw` `crawler.py` | 其 `zsml/rs/dws.do` 接口封装（form 参数结构、分页逻辑）可直接移植到我们 `parsers/` 下的研招网 parser |
| **异步 + 限速 + 代理** | `freecho/yzw` `crawler.py` + `proxy_manager.py` | 我们的 `utils/http.py` 参考其随机延时（0.8~1.2 倍率）、断点续抓（breakpoint 变量）、失败日志机制 |
| **CAS 登录流程** | `freecho/yzw` `login.py` | 研招网部分接口需登录，其 CAS cookie 管理流程可直接复用 |
| **研招网字段映射** | `freecho/yzw` `entity.py` | 字段名 `zdjs`(指导教师)/`zymc`(专业)/`yjfxmc`(研究方向)/`nzsrsstr`(招生人数) 等已与研招网 API 对齐 |
| **导师详情数据模型** | `zengkaipeng/CSLabInfo2022` Markdown 模板 | 输出格式参考（研究方向→报名流程→联系方式的字段顺序） |
| **Scrapy Item 定义** | `Hthing/yzw` `items.py` | 字段完整性校验清单（确保我们 Schema 不遗漏关键字段） |

### 延伸数据源（未来叠加层）
| 数据 | 来源 | 何时接入 |
|---|---|---|
| 导师匿名口碑评价（7.5万条） | `KeGong-XKK/advisor-eval` | 项目跑通后，作为"导师口碑"附加字段 |
| CS 保研实验室/导师招生广告 | `zengkaipeng/CSLabInfo2022` | 机械/自动化方向参考其众包采集模式 |

---

## 三、关键发现与策略调整建议

### 🔑 最大发现：研招网专业目录比"公示名单"更好用
`freecho/yzw` 的实践表明，研招网"招生专业目录"（`yz.chsi.com.cn/zsml/`）**本身就包含指导教师字段**，且覆盖全国所有院校所有专业，数据结构化程度远高于各校五花八门的"招生导师公示"。

**建议策略调整**：
- **第二数据源（原"研究生院公示"）改为"研招网专业目录"**——结构化、全覆盖、有现成爬虫可参考，比逐校爬公示页的 ROI 高一个数量级
- 仍保留 `parsers/` 的插件化设计，新增一个 `parsers/yzw_major_directory.py` 专门对接研招网
- 各校研究生院公示作为**第三层数据**（如需要最终权威名单时再按需补抓），优先级下调

### ⚠️ 注意事项
1. 研招网部分页面需 CAS 登录（`freecho/yzw` 已有 `login.py`，需准备账号）
2. 研招网接口可能更新（xx025/yanx 最后更新 2023，freecho/yzw 2026 仍在维护——优先参考后者）
3. 研招网数据是"招生专业目录"：按专业×学校×院系组织，**指导教师字段并非每校都有**（部分学校只写院系不写具体导师），覆盖率需实测统计

### 📋 下一步行动
1. 从 `freecho/yzw` 复制 `school_level.py` 到我们 `config/`，整理为 `schools.py` 的学校列表骨架
2. 从 `xx025/yanx` 下载 `院校库.csv`，补充学校代码/省份信息
3. 实测研招网接口 `zsml/rs/dws.do` 当前是否可用（2026年9月的最新接口参数）
4. 若研招网导师字段覆盖率足够（>60%的学校写了具体导师名），将研招网作为"招生情况"的主数据源，原"研究生院公示"降级为补充
