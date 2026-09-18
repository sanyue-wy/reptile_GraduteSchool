"""Education domain profile for V3.0 - domain-specific schema extensions.

These fields extend the generic NormalizedRecordDTO for education data.
They are NOT required for all datasets - only when schema_id matches
an education profile (e.g., 'education.tutor.v1', 'education.major.v1').
"""

from dataclasses import dataclass, field
from typing import Any


# Education schema IDs
EDUCATION_TUTOR_V1 = "education.tutor.v1"
EDUCATION_MAJOR_V1 = "education.major.v1"


@dataclass
class EducationTutorFields:
    """Field definitions for education.tutor.v1 schema.

    These are the expected fields in NormalizedRecordDTO.fields
    when schema_id == 'education.tutor.v1'.
    """
    university: str = ""          # 大学名称
    college: str = ""             # 学院名称
    category: str = ""            # 专业类别/学科
    year: int = 0                 # 采集年份
    name: str = ""                # 教师姓名
    title: str = ""               # 职称
    research: str = ""            # 研究方向
    profile_url: str = ""         # 详情页链接
    source_type: str = ""         # "官网师资页" | "研招网"
    email: str = ""               # 邮箱（如有）
    phone: str = ""               # 电话（如有）
    education_background: str = "" # 学历背景
    honors: list[str] = field(default_factory=list)  # 荣誉称号
    projects: list[str] = field(default_factory=list) # 科研项目
    papers: list[str] = field(default_factory=list)   # 代表性论文


@dataclass
class EducationMajorFields:
    """Field definitions for education.major.v1 schema (研招网专业)."""
    university: str = ""
    college: str = ""
    category: str = ""
    year: int = 0
    major_code: str = ""          # 专业代码
    major_name: str = ""          # 专业名称
    degree_type: str = ""         # 学位类型（学硕/专硕）
    duration: str = ""            # 学制
    tuition: str = ""             # 学费
    exam_subjects: list[str] = field(default_factory=list)  # 考试科目
    enrollment: int = 0           # 计划招生数
    contact: str = ""             # 联系方式
    website: str = ""             # 专业网址
    remarks: str = ""             # 备注


# JSON Schema for education.tutor.v1
TUTOR_V1_SCHEMA = {
    "type": "object",
    "properties": {
        "university": {"type": "string"},
        "college": {"type": "string"},
        "category": {"type": "string"},
        "year": {"type": "integer", "minimum": 2000, "maximum": 2100},
        "name": {"type": "string"},
        "title": {"type": "string"},
        "research": {"type": "string"},
        "profile_url": {"type": "string", "format": "uri"},
        "source_type": {"type": "string", "enum": ["官网师资页", "研招网"]},
        "email": {"type": "string", "format": "email"},
        "phone": {"type": "string"},
        "education_background": {"type": "string"},
        "honors": {"type": "array", "items": {"type": "string"}},
        "projects": {"type": "array", "items": {"type": "string"}},
        "papers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["university", "college", "category", "year", "name", "source_type"],
    "additionalProperties": True,  # Allow extra fields for extensibility
}


# JSON Schema for education.major.v1
MAJOR_V1_SCHEMA = {
    "type": "object",
    "properties": {
        "university": {"type": "string"},
        "college": {"type": "string"},
        "category": {"type": "string"},
        "year": {"type": "integer", "minimum": 2000, "maximum": 2100},
        "major_code": {"type": "string"},
        "major_name": {"type": "string"},
        "degree_type": {"type": "string"},
        "duration": {"type": "string"},
        "tuition": {"type": "string"},
        "exam_subjects": {"type": "array", "items": {"type": "string"}},
        "enrollment": {"type": "integer", "minimum": 0},
        "contact": {"type": "string"},
        "website": {"type": "string", "format": "uri"},
        "remarks": {"type": "string"},
    },
    "required": ["university", "college", "category", "year", "major_code", "major_name"],
    "additionalProperties": True,
}


SCHEMA_REGISTRY = {
    EDUCATION_TUTOR_V1: TUTOR_V1_SCHEMA,
    EDUCATION_MAJOR_V1: MAJOR_V1_SCHEMA,
}


def get_education_schema(schema_id: str) -> dict[str, Any]:
    """Get JSON Schema for an education profile."""
    schema = SCHEMA_REGISTRY.get(schema_id)
    if schema is None:
        raise ValueError(f"Unknown education schema_id: {schema_id}")
    return schema


def validate_education_fields(schema_id: str, fields: dict[str, Any]) -> bool:
    """Validate education fields against registered schema."""
    import jsonschema
    schema = SCHEMA_REGISTRY.get(schema_id)
    if schema is None:
        raise ValueError(f"Unknown education schema_id: {schema_id}")
    jsonschema.validate(fields, schema)
    return True