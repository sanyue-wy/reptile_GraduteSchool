import json

with open('verified_urls.json', 'r', encoding='utf-8') as f:
    verified = json.load(f)

# Add missing verified URLs from earlier exploration
missing = {
    '东南大学': {
        'mechanical': {
            'college': '机械工程学院',
            'list_url': 'https://me.seu.edu.cn/szdw/list.htm',
            'list_type': 'static_html',
            'list_item_selector': 'table.wp_article_list_table td',
            'list_name_selector': 'a',
            'list_research_selector': '',
            'detail_selectors': {
                'name': '.jsbt',
                'title': '.carrer .title',
                'department': '.carrer .text:contains("所在院系")',
                'phone': '.carrer .text:contains("电话")',
                'email': '.carrer .text:contains("邮箱")',
                'research': '.news_box .tit:contains("研究方向") + .con'
            }
        }
    },
    '北京理工大学': {
        'mechanical': {
            'college': '机械与车辆学院',
            'list_url': 'https://me.bit.edu.cn/szdw/jsml/jlgcx/index.htm',
            'list_type': 'static_html',
            'list_item_selector': 'dd a[href*="bssds"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': 'h3',
                'title': 'table tr:nth-child(2) td:nth-child(2)',
                'department': 'table tr:nth-child(3) td:nth-child(2)',
                'email': 'table tr:nth-child(9) td:nth-child(2)',
                'phone': 'table tr:nth-child(8) td:nth-child(2)',
                'research': 'table tr:nth-child(11) td:nth-child(2)'
            }
        },
        'automation': {
            'college': '机械与车辆学院',
            'list_url': 'https://me.bit.edu.cn/szdw/jsml/jlgcx/index.htm',
            'list_type': 'static_html',
            'list_item_selector': 'dd a[href*="bssds"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': 'h3',
                'title': 'table tr:nth-child(2) td:nth-child(2)',
                'department': 'table tr:nth-child(3) td:nth-child(2)',
                'email': 'table tr:nth-child(9) td:nth-child(2)',
                'phone': 'table tr:nth-child(8) td:nth-child(2)',
                'research': 'table tr:nth-child(11) td:nth-child(2)'
            }
        }
    },
    '上海交通大学': {
        'mechanical': {
            'college': '机械与动力工程学院',
            'list_url': 'https://me.sjtu.edu.cn/teacher_directory.html',
            'list_type': 'static_html',
            'list_item_selector': 'a[href*="teacher_directory"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': '.tit p, .js-box-item .name',
                'title': '.tit span',
                'department': '.detail p:contains("所在系所")',
                'phone': '.detail p:contains("办公电话")',
                'email': '.detail p:contains("电子邮件")',
                'research': '.js-box-item.on .txt, .js-box-item .txt'
            }
        },
        'automation': {
            'college': '电气工程学院',
            'list_url': 'https://see.sjtu.edu.cn/active/ajax_teacher_list.html',
            'list_type': 'ajax_api',
            'api_params': {'cat_id': '40', 'cat_code': 'jiaoshiml', 'type': '2'},
            'detail_selectors': {
                'name': '.tit p',
                'title': '.tit span',
                'phone': '.detail p:contains("办公电话")',
                'email': '.detail p:contains("电子邮件")',
                'address': '.detail p:contains("通讯地址")',
                'research': '.js-box-item.on .txt'
            }
        }
    },
    '清华大学': {
        'mechanical': {
            'college': '机械工程系',
            'list_url': 'https://me.tsinghua.edu.cn/szdw/zzjs.htm',
            'list_type': 'static_html',
            'list_item_selector': 'div.tea-text a',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': '.t-info-text .name',
                'title': '.t-info-text p:contains("技术职务")',
                'email': '.t-info-text p:contains("电子邮件")',
                'address': '.t-info-text p:contains("通讯地址")',
                'research': '.tab-con .list:nth-child(3) .v_news_content'
            }
        },
        'automation': {
            'college': '自动化系',
            'list_url': 'https://au.tsinghua.edu.cn/szdw/zzjs.htm',
            'list_type': 'static_html',
            'list_item_selector': 'div.tea-text a',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': '.t-info-text .name',
                'title': '.t-info-text p:contains("技术职务")',
                'email': '.t-info-text p:contains("电子邮件")',
                'address': '.t-info-text p:contains("通讯地址")',
                'research': '.tab-con .list:nth-child(3) .v_news_content'
            }
        }
    },
    '浙江大学': {
        'mechanical': {
            'college': '机械工程学院',
            'list_url': 'http://www.mech.sdu.edu.cn/szdw/xssz.htm',
            'list_type': 'static_html',
            'list_item_selector': 'a[href*="teacher"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {}
        },
        'automation': {
            'college': '控制科学与工程学院',
            'list_url': 'http://control.sdu.edu.cn/szdw1.htm',
            'list_type': 'static_html',
            'list_item_selector': 'a[href*="teacher"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {}
        }
    },
    '复旦大学': {
        'mechanical': {
            'college': '智能机器人与先进制造创新学院',
            'list_url': 'https://ciram.fudan.edu.cn/cslm/list.htm',
            'list_type': 'static_html',
            'list_item_selector': 'a[href*="/page.htm"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': '.tit, h1, .name',
                'title': '.tit span, .title',
                'research': '.research, .interest'
            }
        },
        'automation': {
            'college': '微电子学院',
            'list_url': 'https://sme.fudan.edu.cn/szdw/list.htm',
            'list_type': 'static_html',
            'list_item_selector': 'a[href*="teacher"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {}
        }
    },
    '南京大学': {
        'mechanical': {
            'college': '机器人与自动化学院',
            'list_url': 'https://ra.nju.edu.cn/szll/zzjs/index.html',
            'list_type': 'static_html',
            'list_item_selector': 'a[href*="i335"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': 'h1, .name, .tit',
                'title': '.job, .title',
                'education': '.education .nr',
                'research': '.education .nr p:contains("主要")'
            }
        },
        'automation': {
            'college': '机器人与自动化学院',
            'list_url': 'https://ra.nju.edu.cn/szll/zzjs/index.html',
            'list_type': 'static_html',
            'list_item_selector': 'a[href*="i335"]',
            'list_name_selector': 'text',
            'list_research_selector': '',
            'detail_selectors': {
                'name': 'h1, .name, .tit',
                'title': '.job, .title',
                'education': '.education .nr',
                'research': '.education .nr p:contains("主要")'
            }
        }
    }
}

# Merge
verified.update(missing)

with open('verified_urls.json', 'w', encoding='utf-8') as f:
    json.dump(verified, f, ensure_ascii=False, indent=2)

print(f'Total schools in verified_urls.json: {len(verified)}')