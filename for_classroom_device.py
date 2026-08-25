import main
import json
from zip_operator import zip_read
import json_operator
import time
import easygui
import gui
import subprocess
import sys
import os
import ctypes
import logging
from datetime import datetime
from logging_setup import configure_logging

python_path = sys.executable
DAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
logger = logging.getLogger(__name__)
configure_logging()


if os.name == "nt":
    ctypes.windll.kernel32.SetConsoleCP(65001)
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


if os.path.exists(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.json')):
    config = json_operator.read_json(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.json'))
else:
    easygui.msgbox(f'欢迎使用本软件，即将引导配置这台设备，如需重新配置，请删除{os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.json')}', '配置向导')
    config = {}
    config['grade'] = easygui.integerbox('请输入设备所在的年级', '配置向导', lowerbound=1, upperbound=20)
    config['class'] = easygui.integerbox('请输入设备所在的班级', '配置向导', lowerbound=1, upperbound=20)
    config['device_name'] = easygui.enterbox('请输入设备名称，本名称仅用于显示，不会用于管理', '配置向导')
    json_operator.write_json(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.json'), config)
    if easygui.ynbox('是否需要重新配置？', '配置向导'):
        os.remove(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config.json'))
        subprocess.Popen([python_path, os.path.abspath(__file__)])
        sys.exit(0)

def get_time(w,h,m):
    return ((w * 24) + h) * 60 + m

def refresh_time():
    global weekday, hour, minute, second, minute_time
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    second = now.second
    weekday = now.weekday()
    minute_time = get_time(weekday, hour, minute)

def read_schedule():
    """从压缩包中读取课程表"""
    class_grade = config.get('grade')
    class_class = config.get('class')
    schedule_json = zip_read(os.path.join(os.path.abspath(os.path.dirname(__file__)), "data", "data.zip"), f'g{class_grade}-c{class_class}/timetable.json')
    if schedule_json is None:
        return None
    try:
        schedule = json.loads(schedule_json.decode("utf-8"))
        return schedule if isinstance(schedule, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        logger.error("年级%s班级%s的课程表格式无效", class_grade, class_class)
        return None

def show_course_details(name, start_time, end_time):
    easygui.msgbox(title="课程详情", msg=f"这节课是{name}，开始时间{start_time},结束时间{end_time}", ok_button="我已知晓这节课为{name}课")

def remind_course(name, start_time, end_time):
    gui.show_reminder(
        f"本节课为{name}",
		delay_seconds=5,
		auto_close_seconds=10,
        on_confirm=lambda: logger.info("用户已确认课程提醒"),
		on_details=lambda: show_course_details(name, start_time, end_time)
    )


def format_schedule(timetable):
    """将课程表格式化为便于阅读的控制台文本。"""
    days = timetable.get("days", [])
    rows = timetable.get("rows", [])
    headers = ["时间"] + [DAY_NAMES[day] for day in days if 0 <= day < len(DAY_NAMES)]
    lines = ["课程表", " | ".join(headers)]
    lines.append("-" * len(lines[-1]))

    for row in rows:
        cells = row.get("cells", {})
        values = [f"{row.get('start', '')}-{row.get('end', '')}"]
        values.extend(cells.get(str(day), "-") or "-" for day in days if 0 <= day < len(DAY_NAMES))
        lines.append(" | ".join(values))
    return "\n".join(lines)


def main():
    global used_hours, used_minutes, used_weekday
    used_time = -1
    schedule_available = None
    schedule_signature = None
    timetable = None
    next_schedule_refresh = 0.0
    logger.info("课堂设备程序已启动")

    while True: 
        refresh_time()
        current_time = time.monotonic()
        if current_time >= next_schedule_refresh:
            logger.info("正在读取课程表")
            timetable = read_schedule()
            next_schedule_refresh = current_time + 20
            if not timetable:
                if schedule_available is not False:
                    logger.warning("暂无可用课程表，程序将继续等待")
                    schedule_available = False
            else:
                if schedule_available is not True:
                    logger.info("课程表读取成功")
                    schedule_available = True
                current_signature = json.dumps(timetable, ensure_ascii=False, sort_keys=True)
                if current_signature != schedule_signature:
                    logger.info("\n%s", format_schedule(timetable))
                    schedule_signature = current_signature

        if not timetable:
            time.sleep(0.3)
            continue
        if minute_time == used_time:
            logger.debug("当前时间 %s %s:%02d 已处理过，无需再次检查", weekday, hour, minute)
            time.sleep(60 - second)
            continue
        logger.debug("开始检查当前时间 %s %s:%02d 对应的课程", weekday, hour, minute)
        for i in timetable["rows"]: 
            if i["cells"].get(str(weekday), None) is not None:
                start_hour = int(str(i["start"]).split(":")[0])
                start_minute = int(str(i["start"]).split(":")[1])
                start_time = get_time(weekday, start_hour, start_minute)
                if start_time <= used_time:
                    continue
                elif start_time == minute_time and used_time < start_time:
                    remind_course(i["cells"][str(weekday)], i["start"], i["end"])
                    used_time = start_time

                else:
                    used_time = start_time
        time.sleep(0.3)

if __name__ == "__main__":
    main()