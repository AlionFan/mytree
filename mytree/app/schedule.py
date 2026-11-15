"""按北京时间、每周空闲日和 1/3/7 天间隔安排复习。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
DEFAULT = {'days': [1, 2, 3, 4, 5, 6, 7], 'time': '19:30'}
INTERVALS = (1, 3, 7)


def now():
    return datetime.now(TZ)


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('请设置空闲日与时间')
    days, clock = value.get('days'), value.get('time')
    if not isinstance(days, list) or not days or any(type(d) is not int or d not in range(1, 8) for d in days):
        raise ValueError('至少选择一个空闲日')
    import re
    if not isinstance(clock, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock):
        raise ValueError('时间格式应为 HH:MM')
    return {'days': sorted(set(days)), 'time': clock}


def next_slot(availability, stage=0, after=None):
    anchor = after or now()
    start = anchor + timedelta(days=INTERVALS[min(stage, 2)])
    hour, minute = map(int, availability['time'].split(':'))
    slot = start.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(8):
        if slot.isoweekday() in availability['days'] and slot > anchor:
            return slot.isoformat(timespec='minutes')
        slot += timedelta(days=1)
    raise ValueError('没有可用的复习时段')
