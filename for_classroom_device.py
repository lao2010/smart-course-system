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
from datetime import datetime

python_path = sys.executable

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
    global weekday, hour, minute, minute_time
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()
    minute_time = get_time(weekday, hour, minute)

def read_schedule():
    """从压缩包中读取课程表"""
    class_grade = config.get('grade')
    class_class = config.get('class')
    schedule_json = zip_read(os.path.join(os.path.abspath(os.path.dirname(__file__)), "data", "data.zip"), f'g{class_grade}-c{class_class}/timetable.json')
    print(f"读取课程表：年级{class_grade}，班级{class_class}，结果：{schedule_json is not None}")
    print(f"读取课程表：年级{class_grade}，班级{class_class}，结果：\n{schedule_json}")
    if schedule_json is None:
        return None
    try:
        schedule = json.loads(schedule_json.decode("utf-8"))
        return schedule if isinstance(schedule, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        print("解析课程表失败，请检查课程表文件是否正确")
        return None

def show_course_details(name, start_time, end_time):
    easygui.msgbox(title="课程详情", msg=f"这节课是{name}，开始时间{start_time},结束时间{end_time}", ok_button="我已知晓这节课为{name}课")

def remind_course(name, start_time, end_time):
    gui.show_reminder(
        f"本节课为{name}",
		delay_seconds=5,
		auto_close_seconds=10,
        on_confirm=lambda: print("已确认提醒"),
		on_details=lambda: show_course_details(name, start_time, end_time)
    )
1212
def main():
    global used_hours, used_minutes, used_weekday
    used_time = -1

    while True:
        refresh_time()
        timetable = read_schedule()
        if not timetable:
            time.sleep(0.3)
            continue
        for i in timetable["rows"]:
            if i["cells"].get(str(weekday), None) is not None:
                start_hour = int(str(i["start"]).split(":")[0])
                start_minute = int(str(i["start"]).split(":")[1])
                start_time = get_time(weekday, start_hour, start_minute)
                if start_time <= used_time:
                    continue
                elif start_time == minute_time:
                    remind_course(i["cells"][str(weekday)], i["start"], i["end"])
                    used_time = start_time

                else:
                    used_time = start_time
        time.sleep(0.3)

329084049-5834
1+1 == 11
if __name__ == "__main__":
    main()