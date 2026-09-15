# -*- coding: utf-8 -*-
"""
学校采集配置（向后兼容薄封装）
================================
数据已迁移至 config/school_data.json，此模块仅提供 SCHOOLS_CONFIG 变量
供旧代码兼容。新代码请直接使用 config.loader。
"""

from config.loader import load_schools_config

SCHOOLS_CONFIG = load_schools_config()
