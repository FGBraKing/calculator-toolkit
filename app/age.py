"""Days lived so far, the zodiac sign and the next birthday."""

from __future__ import annotations

from datetime import date

from lunardate import LunarDate

from app import common
from app.calculator import InputError

# (month, day, 星座) 为各星座在一年中的起始日；1 月 1–19 日落在摩羯座
ZODIACS = ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪")

_SIGN_STARTS = (
    (1, 20, "水瓶座"),
    (2, 19, "双鱼座"),
    (3, 21, "白羊座"),
    (4, 20, "金牛座"),
    (5, 21, "双子座"),
    (6, 22, "巨蟹座"),
    (7, 23, "狮子座"),
    (8, 23, "处女座"),
    (9, 23, "天秤座"),
    (10, 24, "天蝎座"),
    (11, 23, "射手座"),
    (12, 22, "摩羯座"),
)


def constellation(month: int, day: int) -> str:
    sign = "摩羯座"
    for start_month, start_day, name in _SIGN_STARTS:
        if (month, day) >= (start_month, start_day):
            sign = name
        else:
            break
    return sign


def zodiac(birth: date) -> tuple[str, int]:
    """生肖按农历年划分（春节换年），返回 (生肖, 农历年)。"""
    lunar_year = LunarDate.from_solar_date(birth.year, birth.month, birth.day).year
    return ZODIACS[(lunar_year - 4) % 12], lunar_year


def calculate(payload: dict[str, str], *, as_of: date | None = None) -> dict[str, object]:
    birth = common.day(payload.get("birth"), "birth", "出生日期")
    today = as_of or date.today()
    if birth > today:
        raise InputError("birth", "出生日期不能晚于今天")
    if birth.year < 1901:
        raise InputError("birth", "出生日期超出可计算范围")

    days = (today - birth).days
    age = _full_years(birth, today)
    next_birthday, until_next = _next_birthday(birth, today)
    sign = constellation(birth.month, birth.day)
    animal, lunar_year = zodiac(birth)

    facts = [
        f"出生于 {birth.isoformat()}",
        f"下次生日 {next_birthday.isoformat()}（{until_next} 天后）",
    ]
    formula = "\n".join(
        [
            "出生至今天数 = 今天 − 出生日期",
            f"  = {today.isoformat()} − {birth.isoformat()} = {days:,} 天（不含出生当天）",
            f"周岁 = 已满整年 = {age} 岁",
            f"星座按出生公历月日查表：{birth.month} 月 {birth.day} 日 → {sign}",
            f"生肖按农历年划分：农历 {lunar_year} 年 → {animal}",
        ]
    )
    return common.response(
        primary=f"{days:,}",
        primary_unit="天",
        facts=facts,
        metrics=[
            ("周岁", f"{age} 岁"),
            ("星座", sign),
            ("生肖", animal),
        ],
        formula=formula,
        note="按公历自然日计算，不含出生当天；星座按公历出生月日划分（边界日期以常见划分表为准）；生肖按农历年（春节换年）划分，春节前出生者按上一农历年计。",
    )


def _full_years(birth: date, today: date) -> int:
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


def _next_birthday(birth: date, today: date) -> tuple[date, int]:
    for year in (today.year, today.year + 1, today.year + 2):
        candidate = _birthday_in(year, birth.month, birth.day)
        if candidate >= today:
            return candidate, (candidate - today).days
    raise AssertionError("next birthday is always within two years")


def _birthday_in(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        # 2 月 29 日出生者在平年按 3 月 1 日过一次生日
        return date(year, 3, 1)
