"""Provincial 养老金计发基数 presets for the new-person pension estimate.

Values are public summaries of each province's yearly 计发基数 (the base used
for 基础养老金 of new retirees). Most entries are the 2025 figure; a few
provinces have not published 2025 yet and keep their 2024 figure, marked by
the ``year`` field. Cities that share the provincial base are merged into one
entry; only places that publish a separate base (沈阳、大连、长春、菏泽、武汉、
深圳) get their own entry.

The preset is a starting point: users can always overwrite the number.
"""

from __future__ import annotations

# (code, name, 计发基数 元/月, 数据年度)
REGIONS = (
    ("beijing", "北京", "12049", 2025),
    ("tianjin", "天津", "9417", 2025),
    ("hebei", "河北", "7410", 2025),
    ("shanxi", "山西", "7253", 2025),
    ("neimenggu", "内蒙古", "8179", 2025),
    ("liaoning", "辽宁（不含沈阳、大连）", "7346", 2025),
    ("shenyang", "辽宁 · 沈阳", "8390", 2025),
    ("dalian", "辽宁 · 大连", "8956", 2025),
    ("jilin", "吉林（不含长春）", "7322", 2025),
    ("changchun", "吉林 · 长春", "7978", 2025),
    ("heilongjiang", "黑龙江", "7570", 2025),
    ("shanghai", "上海", "12434", 2025),
    ("jiangsu", "江苏", "8917", 2025),
    ("zhejiang", "浙江", "8433", 2025),
    ("anhui", "安徽", "7999", 2025),
    ("fujian", "福建", "7932", 2025),
    ("jiangxi", "江西", "7054", 2025),
    ("shandong", "山东（不含菏泽）", "7831", 2025),
    ("heze", "山东 · 菏泽", "7506", 2025),
    ("henan", "河南", "6738", 2025),
    ("hubei", "湖北（不含武汉）", "7100", 2024),
    ("wuhan", "湖北 · 武汉", "9037", 2024),
    ("hunan", "湖南", "7694", 2025),
    ("guangdong", "广东（不含深圳）", "9493", 2025),
    ("shenzhen", "广东 · 深圳", "11293", 2025),
    ("guangxi", "广西", "6983", 2025),
    ("hainan", "海南", "8188", 2025),
    ("chongqing", "重庆", "8160", 2024),
    ("sichuan", "四川", "8462", 2025),
    ("guizhou", "贵州", "7324.5", 2025),
    ("yunnan", "云南", "8265", 2025),
    ("xizang", "西藏", "11777", 2025),
    ("shaanxi", "陕西", "7881", 2025),
    ("gansu", "甘肃", "7746", 2025),
    ("qinghai", "青海", "9056", 2025),
    ("ningxia", "宁夏", "8366", 2025),
    ("xinjiang", "新疆", "8448", 2025),
)

NOTE = (
    "预置值为各省养老金计发基数的公开汇总（多数为 2025 年，个别省份仍为 2024 年），"
    "仅供起算；请以当地人社部门最新公布为准，可直接修改。本工具用同一个数作为缴费指数分母与基础养老金基数。"
)


def as_options() -> list[dict[str, object]]:
    return [
        {"code": code, "name": name, "base": base, "year": year}
        for code, name, base, year in REGIONS
    ]
