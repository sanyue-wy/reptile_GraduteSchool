"""专业代码映射表

从学科门类代码（国家标准）到内部 category 的映射。
"""

MAJOR_MAPPING = {
    "mechanical": {
        "name": "机械工程",
        "first_level_codes": ["0855", "0802", "0824"],
        "detail_codes": ["085501", "085502", "080201", "080202", "080203", "080204"],
    },
    "automation": {
        "name": "控制科学与工程",
        "first_level_codes": ["0854", "0811", "0839", "0810"],
        "detail_codes": ["085400", "081100", "081101", "081102", "081103", "081104", "083900", "081000"],
    },
}


def get_major_codes(category: str, level: str = "detail") -> list:
    """
    获取指定类别的专业代码列表。

    Args:
        category: "mechanical" | "automation"
        level: "first_level" | "detail"（默认 detail）

    Returns:
        List[str] 专业代码列表
    """
    info = MAJOR_MAPPING.get(category)
    if not info:
        return []
    return info.get(f"{level}_codes", info.get("detail_codes", []))
