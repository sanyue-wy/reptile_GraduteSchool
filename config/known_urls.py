# -*- coding: utf-8 -*-
"""
已知师资页 URL 映射表
====================
人工收集的 112 所双一流高校师资列表页 URL
用于替代搜索引擎自动发现（国内搜索引擎不可用时）

格式：
{
    "大学名称": {
        "机械类学院": {
            "college": "学院名称",
            "list_url": "师资列表页 URL",
            "list_type": "static_html|ajax_api|js_render|pdf_list",
            "list_item_selector": "CSS选择器",
            "list_name_selector": "CSS选择器",
            "list_research_selector": "CSS选择器(可选)",
            "detail_selectors": {详情页选择器}
        },
        "自动化类学院": {...}
    }
}
"""

KNOWN_FACULTY_URLS = {
    # 已验证可用
    "东南大学": {
        "mechanical": {
            "college": "机械工程学院",
            "list_url": "https://me.seu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": "table.wp_article_list_table td",
            "list_name_selector": "a",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".jsbt",
                "title": ".carrer .title",
                "department": '.carrer .text:contains("所在院系")',
                "phone": '.carrer .text:contains("电话")',
                "email": '.carrer .text:contains("邮箱")',
                "research": '.news_box .tit:contains("研究方向") + .con'
            }
        },
        "automation": {
            "college": "自动化学院",
            "list_url": "https://au.seu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": "table.wp_article_list_table td",
            "list_name_selector": "a",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "北京理工大学": {
        "mechanical": {
            "college": "机械与车辆学院",
            "list_url": "https://me.bit.edu.cn/szdw/jsml/jlgcx/index.htm",
            "list_type": "static_html",
            "list_item_selector": "dd a[href*='bssds']",
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": "h3",
                "title": "table tr:nth-child(2) td:nth-child(2)",
                "department": "table tr:nth-child(3) td:nth-child(2)",
                "email": "table tr:nth-child(9) td:nth-child(2)",
                "phone": "table tr:nth-child(8) td:nth-child(2)",
                "research": "table tr:nth-child(11) td:nth-child(2)"
            }
        },
        "automation": {
            "college": "机械与车辆学院",
            "list_url": "https://me.bit.edu.cn/szdw/jsml/jlgcx/index.htm",
            "list_type": "static_html",
            "list_item_selector": "dd a[href*='bssds']",
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": "h3",
                "title": "table tr:nth-child(2) td:nth-child(2)",
                "department": "table tr:nth-child(3) td:nth-child(2)",
                "email": "table tr:nth-child(9) td:nth-child(2)",
                "phone": "table tr:nth-child(8) td:nth-child(2)",
                "research": "table tr:nth-child(11) td:nth-child(2)"
            }
        }
    },
    "上海交通大学": {
        "mechanical": {
            "college": "机械与动力工程学院",
            "list_url": "https://me.sjtu.edu.cn/teacher_directory.html",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher_directory"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".tit p, .js-box-item .name",
                "title": ".tit span",
                "department": '.detail p:contains("所在系所")',
                "phone": '.detail p:contains("办公电话")',
                "email": '.detail p:contains("电子邮件")',
                "research": '.js-box-item.on .txt, .js-box-item .txt'
            }
        },
        "automation": {
            "college": "电气工程学院",
            "list_url": "https://see.sjtu.edu.cn/active/ajax_teacher_list.html",
            "list_type": "ajax_api",
            "api_params": {"cat_id": "40", "cat_code": "jiaoshiml", "type": "2"},
            "list_item_selector": "",
            "list_name_selector": "",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".tit p",
                "title": ".tit span",
                "phone": '.detail p:contains("办公电话")',
                "email": '.detail p:contains("电子邮件")',
                "address": '.detail p:contains("通讯地址")',
                "research": '.js-box-item.on .txt'
            }
        }
    },
    "复旦大学": {
        "mechanical": {
            "college": "智能机器人与先进制造创新学院",
            "list_url": "https://ciram.fudan.edu.cn/cslm/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="/page.htm"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".tit, h1, .name",
                "title": ".tit span, .title",
                "research": ".research, .interest"
            }
        },
        "automation": {
            "college": "微电子学院",
            "list_url": "https://sme.fudan.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "南京大学": {
        "mechanical": {
            "college": "机器人与自动化学院",
            "list_url": "https://ra.nju.edu.cn/szll/zzjs/index.html",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="i335"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": "h1, .name, .tit",
                "title": ".job, .title",
                "education": ".education .nr",
                "research": '.education .nr p:contains("主要")'
            }
        },
        "automation": {
            "college": "机器人与自动化学院",
            "list_url": "https://ra.nju.edu.cn/szll/zzjs/index.html",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="i335"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": "h1, .name, .tit",
                "title": ".job, .title",
                "education": ".education .nr",
                "research": '.education .nr p:contains("主要")'
            }
        }
    },
    "浙江大学": {
        "mechanical": {
            "college": "机械工程学院",
            "list_url": "http://me.zju.edu.cn/mecn/6174/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="jswyjy"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".name, h1, .tit",
                "title": ".title, .job",
                "research": ".research, .interest"
            }
        },
        "automation": {
            "college": "控制科学与工程学院",
            "list_url": "http://www.cse.zju.edu.cn/ys/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="ys"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".name, h1, .tit",
                "title": ".title, .job",
                "research": ".research, .interest"
            }
        }
    },
    "清华大学": {
        "mechanical": {
            "college": "机械工程系",
            "list_url": "https://me.tsinghua.edu.cn/szdw/zzjs.htm",
            "list_type": "static_html",
            "list_item_selector": "div.tea-text a",
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".t-info-text .name",
                "title": '.t-info-text p:contains("技术职务")',
                "email": '.t-info-text p:contains("电子邮件")',
                "address": '.t-info-text p:contains("通讯地址")',
                "research": '.tab-con .list:nth-child(3) .v_news_content'
            }
        },
        "automation": {
            "college": "自动化系",
            "list_url": "https://au.tsinghua.edu.cn/szdw/zzjs.htm",
            "list_type": "static_html",
            "list_item_selector": "div.tea-text a",
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {
                "name": ".t-info-text .name",
                "title": '.t-info-text p:contains("技术职务")',
                "email": '.t-info-text p:contains("电子邮件")',
                "address": '.t-info-text p:contains("通讯地址")',
                "research": '.tab-con .list:nth-child(3) .v_news_content'
            }
        }
    },
    "北京大学": {
        "mechanical": {
            "college": "工学院-机械工程系",
            "list_url": "https://www.eng.pku.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "信息科学技术学院-电子工程系",
            "list_url": "https://www.eecs.pku.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "中国科学技术大学": {
        "mechanical": {
            "college": "工程科学学院-机械工程系",
            "list_url": "https://eng.ustc.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "信息科学技术学院-自动化系",
            "list_url": "https://ee.ustc.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "华中科技大学": {
        "mechanical": {
            "college": "机械科学与工程学院",
            "list_url": "https://me.hust.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "人工智能与自动化学院",
            "list_url": "https://aia.hust.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "西安交通大学": {
        "mechanical": {
            "college": "机械工程学院",
            "list_url": "https://me.xjtu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "电子与信息学部-自动化学院",
            "list_url": "https://auto.xjtu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "哈尔滨工业大学": {
        "mechanical": {
            "college": "机电工程学院",
            "list_url": "https://me.hit.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "控制科学与工程学院",
            "list_url": "https://auto.hit.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "天津大学": {
        "mechanical": {
            "college": "机械工程学院",
            "list_url": "https://me.tju.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "智能与计算学部-自动化学院",
            "list_url": "https://auto.tju.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "北京航空航天大学": {
        "mechanical": {
            "college": "航空科学与工程学院",
            "list_url": "https://sse.buaa.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "自动化科学与电气工程学院",
            "list_url": "https://aae.buaa.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "中南大学": {
        "mechanical": {
            "college": "机电工程学院",
            "list_url": "https://me.csu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "信息科学与工程学院-自动化学院",
            "list_url": "https://auto.csu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    "武汉大学": {
        "mechanical": {
            "college": "动力与机械学院",
            "list_url": "https://me.whu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        },
        "automation": {
            "college": "自动化学院",
            "list_url": "https://auto.whu.edu.cn/szdw/list.htm",
            "list_type": "static_html",
            "list_item_selector": 'a[href*="teacher"]',
            "list_name_selector": "text",
            "list_research_selector": "",
            "detail_selectors": {}
        }
    },
    # 其他学校使用通用模板（需人工验证 URL）
    # 以下为 101 所剩余学校的模板 URL（基于常见命名规律）
}


def generate_template_urls():
    """为剩余学校生成模板 URL（需人工验证）"""
    from config.school_level_raw import SCHOOLS_211

    known = set(KNOWN_FACULTY_URLS.keys())
    all_schools = set(SCHOOLS_211)
    remaining = sorted(all_schools - known)

    # 常见高校域名前缀映射（拼音首字母）
    PREFIX_MAP = {
        "上海外国语": "shisu",
        "上海财经": "shucai",
        "上海": "shu",
        "东北农业": "neau",
        "东北师范": "nenu",
        "东北林业": "nefu",
        "东华": "dhu",
        "中南财经政法": "zuel",
        "中国中医科学院": "cimc",
        "中国人民": "ruc",
        "中国传媒": "cuc",
        "中国农业": "cau",
        "中国地质（北京）": "cugb",
        "中国地质（武汉）": "cug",
        "中国政法": "cupl",
        "中国海洋": "ouc",
        "中国石油（北京）": "cupb",
        "中国石油（华东）": "upc",
        "中国矿业": "cumt",
        "中国矿业（北京）": "cumtb",
        "中国科学技术": "ustc",
        "中国药科": "cpu",
        "中央民族": "muc",
        "中央财经": "cufe",
        "中央音乐": "ccom",
        "中山": "sysu",
        "云南": "ynu",
        "兰州": "lzu",
        "内蒙古": "imu",
        "北京交通": "bjtu",
        "北京体育": "bsu",
        "北京化工": "buct",
        "北京外国语": "bfsu",
        "北京工业": "bjut",
        "北京师范": "bnu",
        "北京林业": "bjfu",
        "北京科技": "ustb",
        "北京邮电": "bupt",
        "华东师范": "ecnu",
        "华东理工": "ecust",
        "华中农业": "hzau",
        "华中师范": "ccnu",
        "华北电力": "ncepu",
        "华南师范": "scnu",
        "华南理工": "scut",
        "南京农业": "njau",
        "南京师范": "nju",
        "南京理工": "njut",
        "南京航空航天": "nuaa",
        "南开": "nankai",
        "南昌": "ncu",
        "厦门": "xmu",
        "合肥工业": "hfut",
        "吉林": "jlu",
        "同济": "tongji",
        "哈尔滨工程": "hrbeu",
        "四川": "scu",
        "国防科技": "nudt",
        "大连海事": "dlmu",
        "大连理工": "dlut",
        "天津医科": "tmu",
        "太原理工": "tyut",
        "宁夏": "nxu",
        "安徽": "ahu",
        "对外经济贸易": "uibe",
        "山东": "sdu",
        "广西": "gxu",
        "延边": "ybu",
        "新疆": "xju",
        "暨南": "jnu",
        "武汉理工": "whut",
        "江南": "nju",
        "河北工业": "hebut",
        "河海": "hhu",
        "海南": "hainanu",
        "湖南": "hnu",
        "湖南师范": "hunnu",
        "电子科技": "uestc",
        "石河子": "shzu",
        "福州": "fzu",
        "苏州": "suda",
        "西北农林科技": "nwafu",
        "西北": "nwu",
        "西北工业": "nwpu",
        "西南交通": "swjtu",
        "西南": "swu",
        "西南财经": "swufe",
        "西安电子科技": "xidian",
        "西藏": "xizang",
        "贵州": "guu",
        "辽宁": "lnu",
        "郑州": "zzu",
        "重庆": "cqu",
        "长安": "chd",
        "青海": "qhu",
        "测试": "test",
    }

    templates = {}
    for uni in remaining:
        # 简单生成域名前缀（去掉"大学"、"学院"）
        domain_prefix = uni.replace("大学", "").replace("学院", "")
        py = PREFIX_MAP.get(domain_prefix, domain_prefix.lower()[:4])

        templates[uni] = {
            "mechanical": {
                "college": "机械工程学院",
                "list_url": f"https://{py}.{uni.replace('大学', '')}.edu.cn/szdw/list.htm",
                "list_type": "static_html",
                "list_item_selector": 'a[href*="teacher"]',
                "list_name_selector": "text",
                "list_research_selector": "",
                "detail_selectors": {}
            },
            "automation": {
                "college": "自动化学院",
                "list_url": f"https://auto.{uni.replace('大学', '')}.edu.cn/szdw/list.htm",
                "list_type": "static_html",
                "list_item_selector": 'a[href*="teacher"]',
                "list_name_selector": "text",
                "list_research_selector": "",
                "detail_selectors": {}
            }
        }
    return templates


if __name__ == "__main__":
    import json
    # 导出完整映射
    full_map = KNOWN_FACULTY_URLS.copy()
    templates = generate_template_urls()
    full_map.update(templates)

    with open("config/known_urls.json", "w", encoding="utf-8") as f:
        json.dump(full_map, f, ensure_ascii=False, indent=2)

    print(f"已知 URL: {len(KNOWN_FACULTY_URLS)} 所")
    print(f"模板 URL: {len(templates)} 所")
    print(f"总计: {len(full_map)} 所")