"""配置校验器

校验学校配置是否符合 INTERFACE_SPEC.md 第 4 节规范。
"""

from typing import Dict, List

from utils.errors import is_placeholder_url


class ConfigError:
    """单条配置校验错误"""

    def __init__(self, university: str, college: str, field: str, message: str, level: str = "error"):
        self.university = university
        self.college = college
        self.field = field
        self.message = message
        self.level = level  # "error" | "warning"

    def __str__(self):
        return f"[{self.level.upper()}] {self.university}/{self.college} - {self.field}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "university": self.university,
            "college": self.college,
            "field": self.field,
            "message": self.message,
            "level": self.level,
        }


VALID_CATEGORIES = {"mechanical", "automation"}
VALID_LIST_TYPES = {"static_html", "ajax_api", "js_render", "pdf_list"}

# 占位符 URL 模式（用于启动前配置体检）
PLACEHOLDER_URL_PATTERNS = (
    "x.com",
    "example.com",
    "test.edu.cn",
    "localhost",
    "placeholder",
    "your-domain",
    "http://x",
)


def _safe_get(d: dict, *keys, default=None):
    """安全地获取嵌套字典值"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
        if cur is None:
            return default
    return cur


def _check_placeholder_url(url: str) -> bool:
    """检查 URL 是否为占位符"""
    if not url or not isinstance(url, str):
        return False
    url_lower = url.lower().strip()
    return any(pattern.lower() in url_lower for pattern in PLACEHOLDER_URL_PATTERNS)


def validate_school_config(config: Dict) -> List[ConfigError]:
    """
    校验单校配置是否符合 INTERFACE_SPEC.md 第 4 节规范。

    Args:
        config: 单校配置字典

    Returns:
        List[ConfigError]  # 空列表表示校验通过

    校验规则：
        - university: 非空字符串
        - categories: 非空列表
        - 每个 category 必含: college(非空), category("mechanical"|"automation")
        - faculty.list_url: 非空（静默跳过的需显式标记 enabled=false）
        - faculty.list_type: "static_html" | "ajax_api"
        - notice.enabled: bool
        - notice.template: 非空（当 notice.enabled=true）
        - notice.school_code: 非空（当 notice.enabled=true 且 template="yzw_major"）
    """
    errors: List[ConfigError] = []

    university = config.get("university", "")
    if not university or not isinstance(university, str) or not university.strip():
        errors.append(ConfigError(university or "<unknown>", "", "university", "university 字段不能为空"))

    categories = config.get("categories")
    if not categories:
        errors.append(ConfigError(university, "", "categories", "categories 不能为空列表"))
        return errors  # 没有 categories 无法继续逐项校验

    if not isinstance(categories, list):
        errors.append(ConfigError(university, "", "categories", "categories 必须是列表"))
        return errors

    for cat in categories:
        college = cat.get("college", "")
        category = cat.get("category", "")

        if not isinstance(college, str) or not college.strip():
            errors.append(ConfigError(university, college or "<unknown>", "college", "college 字段不能为空"))

        if category not in VALID_CATEGORIES:
            errors.append(ConfigError(university, college, "category",
                                      f"category 必须是 {VALID_CATEGORIES}，得到: {category!r}"))

        # --- faculty 校验 ---
        faculty = cat.get("faculty", {})
        if not isinstance(faculty, dict):
            errors.append(ConfigError(university, college, "faculty", "faculty 必须是字典"))
        else:
            # list_url: 非空
            list_url = faculty.get("list_url")
            if not list_url or not isinstance(list_url, str) or not list_url.strip():
                # 静默跳过需显式标记 enabled=false — 这里检查 faculty 是否标记为 disabled
                if not faculty.get("enabled", True) is False and not faculty.get("disabled", False):
                    errors.append(ConfigError(university, college, "faculty.list_url",
                                              "list_url 为空，但未标记 disabled，请显式设置 enabled=false 或 disabled=true"))

            # list_type
            list_type = faculty.get("list_type")
            if list_type and list_type not in VALID_LIST_TYPES:
                errors.append(ConfigError(university, college, "faculty.list_type",
                                          f"list_type 必须是 {VALID_LIST_TYPES}，得到: {list_type!r}"))

            # list_url: 占位符检测（启动前体检，error 级）
            if list_url and isinstance(list_url, str) and _check_placeholder_url(list_url):
                errors.append(ConfigError(university, college, "faculty.list_url",
                                          f"list_url 是占位符 '{list_url}'，需替换为真实师资页地址",
                                          level="error"))

        # --- notice 校验 ---
        notice = cat.get("notice", {})
        if not isinstance(notice, dict):
            errors.append(ConfigError(university, college, "notice", "notice 必须是字典"))
            notice = {}
        else:
            enabled = notice.get("enabled")
            if not isinstance(enabled, bool):
                errors.append(ConfigError(university, college, "notice.enabled",
                                          f"notice.enabled 必须是 bool，得到: {enabled!r}"))

            if enabled is True:
                template = notice.get("template")
                if not template or not isinstance(template, str) or not template.strip():
                    errors.append(ConfigError(university, college, "notice.template",
                                              "notice.enabled=true 时 template 不能为空"))

                # 当 template="yzw_major" 时，school_code 必填
                if template == "yzw_major":
                    school_code = notice.get("school_code")
                    if not school_code or not isinstance(school_code, str) or not str(school_code).strip():
                        errors.append(ConfigError(university, college, "notice.school_code",
                                                  "template 为 yzw_major 时 school_code 不能为空"))

    return errors


def validate_all_configs(configs: List[Dict]) -> Dict[str, List]:
    """
    校验全量配置。

    Returns:
        {
            "errors": [ConfigError, ...],     # 必须修复
            "warnings": [ConfigError, ...],   # 建议修复
            "summary": {"total": N, "errors": N, "warnings": N, "ok": N}
        }
    """
    all_errors: List[ConfigError] = []

    for config in configs:
        errors = validate_school_config(config)
        all_errors.extend(errors)

    errors_list = [e for e in all_errors if e.level == "error"]
    warnings_list = [e for e in all_errors if e.level == "warning"]

    summary = {
        "total": len(configs),
        "errors": len(errors_list),
        "warnings": len(warnings_list),
        "ok": len(configs) - len({e.university for e in errors_list}),
    }

    return {
        "errors": errors_list,
        "warnings": warnings_list,
        "summary": summary,
    }
