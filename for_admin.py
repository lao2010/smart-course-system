"""课程表管理器入口。"""

import json
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from zipfile import ZipFile
from datetime import datetime

from zip_operator import zip_change_file
from get_course_from_xlsx import CourseScheduleParser
import main as sync_program


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_PATH = os.path.join(ROOT, "data", "data.zip")
DAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def class_prefix(grade, class_number):
    return f"g{grade}-c{class_number}"


def friendly_class_name(grade, class_number):
    grade_number = int(grade)
    grade_name = f"高{grade_number - 9}" if 10 <= grade_number <= 12 else f"{grade_number}"
    return f"{grade_name}年级{class_number}班"


def ensure_archive():
    os.makedirs(os.path.dirname(ARCHIVE_PATH), exist_ok=True)
    if not os.path.exists(ARCHIVE_PATH):
        with ZipFile(ARCHIVE_PATH, "w"):
            pass


def read_archive_names():
    ensure_archive()
    with ZipFile(ARCHIVE_PATH) as archive:
        return archive.namelist()


def available_classes():
    prefixes = set()
    for name in read_archive_names():
        prefix = name.split("/", 1)[0]
        if prefix.startswith("g") and "-c" in prefix:
            prefixes.add(prefix)
    return sorted(prefixes)


def class_names():
    return load_json("classes.json", {})


def load_json(path, default):
    with ZipFile(ARCHIVE_PATH) as archive:
        try:
            with archive.open(path) as stream:
                return json.loads(stream.read().decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return default


def swap_timetable_days(timetable, first_day, second_day):
    """交换课程表中两个日期的启用状态及所有课程、活动。"""
    if first_day == second_day:
        return timetable

    days = timetable.get("days", [])
    if first_day in days and second_day not in days:
        days.remove(first_day)
        days.append(second_day)
    elif second_day in days and first_day not in days:
        days.remove(second_day)
        days.append(first_day)
    timetable["days"] = sorted(days)

    for row in timetable.get("rows", []):
        cells = row.setdefault("cells", {})
        first_value = cells.get(str(first_day), "")
        second_value = cells.get(str(second_day), "")
        if second_value:
            cells[str(first_day)] = second_value
        else:
            cells.pop(str(first_day), None)
        if first_value:
            cells[str(second_day)] = first_value
        else:
            cells.pop(str(second_day), None)
    return timetable


def choose_swap_days(parent, title):
    """弹出两个日期选择框，返回日期索引或 None。"""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.grab_set()
    result = []
    first = ttk.Combobox(dialog, values=DAY_NAMES, state="readonly", width=8)
    second = ttk.Combobox(dialog, values=DAY_NAMES, state="readonly", width=8)
    first.current(0)
    second.current(1)
    ttk.Label(dialog, text="将以下两天的课程与活动互换：").grid(
        row=0, column=0, columnspan=3, padx=16, pady=(16, 10)
    )
    first.grid(row=1, column=0, padx=(16, 6), pady=6)
    ttk.Label(dialog, text="⇄").grid(row=1, column=1, padx=4)
    second.grid(row=1, column=2, padx=(6, 16), pady=6)

    def confirm():
        if first.current() == second.current():
            messagebox.showerror("提示", "请选择两个不同的日期。", parent=dialog)
            return
        result.extend((first.current(), second.current()))
        dialog.destroy()

    buttons = ttk.Frame(dialog)
    buttons.grid(row=2, column=0, columnspan=3, pady=(8, 16))
    ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
    ttk.Button(buttons, text="确定", command=confirm).pack(side="right", padx=8)
    parent.wait_window(dialog)
    return tuple(result) if result else None


def swap_all_classes(first_day, second_day):
    """交换 ZIP 中全部班级的两个日期。"""
    changed = []
    for prefix in available_classes():
        timetable = load_json(f"{prefix}/timetable.json", None)
        if isinstance(timetable, dict):
            changed.append((prefix, swap_timetable_days(timetable, first_day, second_day)))

    archive_info = load_json("data.json", {})
    if not isinstance(archive_info, dict):
        archive_info = {}
    archive_info["version"] = time.time()
    payloads = {
        f"{prefix}/timetable.json": json.dumps(timetable, ensure_ascii=False, indent=2).encode("utf-8")
        for prefix, timetable in changed
    }
    payloads["data.json"] = json.dumps(archive_info, ensure_ascii=False, indent=2).encode("utf-8")
    for path, content in payloads.items():
        if not zip_change_file(ARCHIVE_PATH, path, content):
            raise OSError(f"无法写入 {path}")
    return len(changed)


def save_class(prefix, timetable, courses=None):
    ensure_archive()
    archive_info = load_json("data.json", {})
    if not isinstance(archive_info, dict):
        archive_info = {}
    archive_info["version"] = time.time()
    payloads = {
        f"{prefix}/timetable.json": json.dumps(timetable, ensure_ascii=False, indent=2).encode("utf-8"),
        "data.json": json.dumps(archive_info, ensure_ascii=False, indent=2).encode("utf-8"),
    }
    if courses is not None:
        payloads["courses.json"] = json.dumps(courses, ensure_ascii=False, indent=2).encode("utf-8")
    for path, content in payloads.items():
        if not zip_change_file(ARCHIVE_PATH, path, content):
            raise OSError(f"无法写入 {path}")


def save_class_names(names):
    content = json.dumps(names, ensure_ascii=False, indent=2).encode("utf-8")
    if not zip_change_file(ARCHIVE_PATH, "classes.json", content):
        raise OSError("无法写入 classes.json")


def delete_class(prefix):
    """删除班级目录，复用 ZIP 操作器完成每个文件的替换流程。"""
    names = [name for name in read_archive_names() if not name.startswith(prefix + "/")]
    temporary = ARCHIVE_PATH + ".tmp"
    try:
        with ZipFile(ARCHIVE_PATH) as source, ZipFile(temporary, "w") as target:
            for info in source.infolist():
                if info.filename in names:
                    target.writestr(info, source.read(info.filename))
        os.replace(temporary, ARCHIVE_PATH)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


class ClassManager(tk.Toplevel):
    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.on_select = on_select
        self.title("班级管理")
        self.geometry("420x360")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", parent.destroy)

        ttk.Label(self, text="选择要编辑的班级", font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(20, 10))
        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", padx=24, pady=(0, 10))
        self.grade_search = tk.StringVar()
        self.class_search = tk.StringVar()
        ttk.Label(search_frame, text="年级").pack(side="left")
        grade_entry = ttk.Entry(search_frame, textvariable=self.grade_search, width=8)
        grade_entry.pack(side="left", padx=(4, 12))
        ttk.Label(search_frame, text="班级").pack(side="left")
        class_entry = ttk.Entry(search_frame, textvariable=self.class_search, width=8)
        class_entry.pack(side="left", padx=(4, 12))
        ttk.Button(search_frame, text="搜索", command=self.search).pack(side="left")
        grade_entry.bind("<Return>", lambda _event: self.search())
        class_entry.bind("<Return>", lambda _event: self.search())
        self.listbox = tk.Listbox(self, height=11, activestyle="dotbox")
        self.listbox.pack(fill="both", expand=True, padx=24)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.select())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=24, pady=16)
        ttk.Button(buttons, text="添加班级", command=self.add).pack(side="left")
        ttk.Button(buttons, text="删除班级", command=self.remove).pack(side="left", padx=8)
        ttk.Button(buttons, text="全系统调换日期", command=self.swap_all_days).pack(side="left")
        ttk.Button(buttons, text="打开", command=self.select).pack(side="right")
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, tk.END)
        self.class_items = []
        names = class_names()
        for prefix in self.filtered_classes():
            self.class_items.append(prefix)
            self.listbox.insert(tk.END, names.get(prefix, prefix))

    def filtered_classes(self):
        grade = self.grade_search.get().strip()
        class_number = self.class_search.get().strip()
        prefixes = available_classes()
        if grade and class_number:
            target = class_prefix(grade, class_number)
            return [prefix for prefix in prefixes if prefix == target]
        if grade:
            return [prefix for prefix in prefixes if prefix.startswith(f"g{grade}-c")]
        if class_number:
            return [prefix for prefix in prefixes if prefix.endswith(f"-c{class_number}")]
        return prefixes

    def search(self):
        self.refresh()

    def add(self):
        grade = simpledialog.askstring("添加班级", "年级：", parent=self)
        class_number = simpledialog.askstring("添加班级", "班级：", parent=self)
        if not grade or not class_number:
            return
        try:
            grade_number = int(grade.strip())
        except ValueError:
            messagebox.showerror("提示", "年级必须是 1 到 12 的数字。", parent=self)
            return
        if not 1 <= grade_number <= 12 or not class_number.strip():
            messagebox.showerror("提示", "年级必须是 1 到 12 的数字，班级不能为空。", parent=self)
            return
        grade = str(grade_number)
        class_number = class_number.strip()
        display_name = friendly_class_name(grade, class_number)
        prefix = class_prefix(grade, class_number)
        if prefix in available_classes():
            messagebox.showinfo("提示", "该班级已经存在。", parent=self)
            return
        save_class(prefix, {"days": [0, 1, 2, 3, 4], "rows": []})
        names = class_names()
        names[prefix] = display_name.strip()
        save_class_names(names)
        logger.info("添加班级: %s", display_name.strip())
        self.refresh()

    def remove(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        prefix = self.class_items[selection[0]]
        if messagebox.askyesno("确认删除", f"确定删除 {prefix} 吗？", parent=self):
            delete_class(prefix)
            names = class_names()
            names.pop(prefix, None)
            save_class_names(names)
            logger.info("删除班级: %s", self.listbox.get(selection[0]))
            self.refresh()

    def select(self):
        selection = self.listbox.curselection()
        if selection:
            self.on_select(self.class_items[selection[0]])

    def swap_all_days(self):
        selected = choose_swap_days(self, "全系统调换日期")
        if not selected:
            return
        first_day, second_day = selected
        if not messagebox.askyesno(
            "确认调换",
            f"确定调换全系统的{DAY_NAMES[first_day]}和{DAY_NAMES[second_day]}吗？",
            parent=self,
        ):
            return
        try:
            count = swap_all_classes(first_day, second_day)
            logger.info("全系统调换日期: %s <-> %s，共 %s 个班级", DAY_NAMES[first_day], DAY_NAMES[second_day], count)
            messagebox.showinfo("调换成功", f"已调换 {count} 个班级的课程与活动。", parent=self)
        except OSError as error:
            messagebox.showerror("调换失败", str(error), parent=self)


class TimetableEditor(tk.Toplevel):
    def __init__(self, manager, prefix):
        super().__init__(manager)
        self.manager = manager
        self.prefix = prefix
        self.display_name = class_names().get(prefix, prefix)
        self.title(f"课程表编辑器 - {self.display_name}")
        self.geometry("1050x620")
        self.minsize(760, 480)
        self.protocol("WM_DELETE_WINDOW", self.open_manager)
        self.rows = []
        self.courses = load_json("courses.json", [])
        timetable = load_json(f"{prefix}/timetable.json", {"days": [0, 1, 2, 3, 4], "rows": []})
        self.day_vars = [tk.BooleanVar(value=index in timetable.get("days", [])) for index in range(7)]
        self.saved_state = None

        self.make_toolbar()
        self.make_day_selector()
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for row in timetable.get("rows", []):
            self.add_row(row)
        if not self.rows:
            self.add_row()
        self.saved_state = self.current_state()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def make_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=16, pady=12)
        ttk.Label(toolbar, text=f"班级：{self.display_name}", font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        ttk.Button(toolbar, text="增加节次", command=self.add_period).pack(side="left", padx=(24, 0))
        ttk.Button(toolbar, text="删除末节", command=self.remove_period).pack(side="left", padx=8)
        ttk.Button(toolbar, text="导入 XLSX", command=self.import_xlsx).pack(side="left", padx=8)
        ttk.Button(toolbar, text="调换日期", command=self.swap_days).pack(side="left", padx=8)
        ttk.Button(toolbar, text="保存", command=self.save).pack(side="right")
        ttk.Button(toolbar, text="打开", command=self.open_manager).pack(side="right", padx=8)
        ttk.Button(toolbar, text="编辑课程", command=self.edit_courses).pack(side="right", padx=8)

    def make_day_selector(self):
        selector = ttk.LabelFrame(self, text="显示日期（可不连续选择，最多 7 天）")
        selector.pack(fill="x", padx=16, pady=(0, 10))
        for index, name in enumerate(DAY_NAMES):
            ttk.Checkbutton(selector, text=name, variable=self.day_vars[index], command=self.render).pack(side="left", padx=10, pady=6)

    def selected_days(self):
        return [index for index, variable in enumerate(self.day_vars) if variable.get()]

    def render(self):
        self.sync_widgets()
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        for row in self.rows:
            row["widgets"] = {}
        days = self.selected_days()
        ttk.Label(self.grid_frame, text="时间").grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
        for column, day in enumerate(days, 1):
            ttk.Label(self.grid_frame, text=DAY_NAMES[day], anchor="center").grid(row=0, column=column, sticky="nsew", padx=3, pady=3)
        for row_index, row in enumerate(self.rows, 1):
            time_frame = ttk.Frame(self.grid_frame)
            time_frame.grid(row=row_index, column=0, sticky="nsew", padx=3, pady=3)
            row["time_entries"] = self.make_time_entries(time_frame, row)
            for column, day in enumerate(days, 1):
                combo = ttk.Combobox(self.grid_frame, values=self.courses, state="readonly", width=18)
                combo.set(row["cells"].get(str(day), ""))
                combo.grid(row=row_index, column=column, sticky="ew", padx=3, pady=3)
                row["widgets"][day] = combo
        for column in range(len(days) + 1):
            self.grid_frame.columnconfigure(column, weight=1)

    def make_time_entries(self, parent, row):
        start = row["start"].get().split(":", 1)
        end = row["end"].get().split(":", 1)
        values = (start[0] if len(start) == 2 else "", start[1] if len(start) == 2 else "",
                  end[0] if len(end) == 2 else "", end[1] if len(end) == 2 else "")
        entries = []
        for index, value in enumerate(values):
            entry = ttk.Entry(parent, width=3, justify="center")
            entry.insert(0, value)
            entry.pack(side="left")
            entries.append(entry)
            if index in (0, 2):
                ttk.Label(parent, text=":").pack(side="left")
            if index == 1:
                ttk.Label(parent, text=" - ").pack(side="left")
        return entries

    def add_row(self, data=None):
        data = data or {"start": "", "end": "", "cells": {}}
        start = tk.StringVar(value=data.get("start", ""))
        end = tk.StringVar(value=data.get("end", ""))
        self.rows.append({"start": start, "end": end, "cells": data.get("cells", {}), "widgets": {}})
        self.render()

    def sync_widgets(self):
        for row in self.rows:
            if "time_entries" in row:
                values = [entry.get().strip() for entry in row["time_entries"]]
                row["start"].set(f"{values[0]}:{values[1]}")
                row["end"].set(f"{values[2]}:{values[3]}")
            for day, widget in row["widgets"].items():
                if widget.winfo_exists():
                    row["cells"][str(day)] = widget.get()

    def collect_rows(self):
        self.sync_widgets()
        result = []
        for row in self.rows:
            result.append({"start": row["start"].get(), "end": row["end"].get(), "cells": row["cells"]})
        return result

    def add_period(self):
        self.add_row()

    def remove_period(self):
        if len(self.rows) <= 1:
            messagebox.showinfo("提示", "课程表至少保留一节课。", parent=self)
            return
        self.sync_widgets()
        self.rows.pop()
        self.render()

    def swap_days(self):
        selected = choose_swap_days(self, "调换当前班级日期")
        if not selected:
            return
        first_day, second_day = selected
        self.sync_widgets()
        timetable = {
            "days": self.selected_days(),
            "rows": self.collect_rows(),
        }
        swap_timetable_days(timetable, first_day, second_day)
        for index, variable in enumerate(self.day_vars):
            variable.set(index in timetable["days"])
        self.rows.clear()
        for data in timetable["rows"]:
            self.rows.append({
                "start": tk.StringVar(value=data.get("start", "")),
                "end": tk.StringVar(value=data.get("end", "")),
                "cells": data.get("cells", {}),
                "widgets": {},
            })
        self.render()
        logger.info("当前班级调换日期（尚未保存）: %s <-> %s", DAY_NAMES[first_day], DAY_NAMES[second_day])

    def import_xlsx(self):
        """导入 XLSX 到当前编辑器，实际写入需点击保存。"""
        file_path = filedialog.askopenfilename(
            parent=self,
            title="选择课程表 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xlsm"), ("所有文件", "*.*")],
        )
        if not file_path:
            return

        try:
            parser = CourseScheduleParser(file_path)
            imported = parser.parse()
            if not imported:
                raise ValueError("未找到有效的课程表。")

            sorted_days = [
                day for day in parser.DAY_ORDER
                if day in parser.day_columns
            ]
            if not sorted_days or not imported["time"]:
                raise ValueError("课程表中没有检测到星期或节次。")

            # 导入的星期映射到编辑器的 0=周一 ... 6=周日。
            for day_index, day_name in enumerate(parser.DAY_ORDER):
                self.day_vars[day_index].set(day_name in sorted_days)

            imported_rows = []
            imported_courses = []
            for row_index, time_value in enumerate(imported["time"]):
                start = end = ""
                if time_value:
                    start = f"{time_value[0]:02d}:{time_value[1]:02d}"
                    end = f"{time_value[2]:02d}:{time_value[3]:02d}"

                cells = {}
                for day_position, day_name in enumerate(sorted_days):
                    day_index = parser.DAY_ORDER.index(day_name)
                    course = imported["list"][day_position][row_index].strip()
                    cells[str(day_index)] = course
                    if course and course not in imported_courses:
                        imported_courses.append(course)

                imported_rows.append({
                    "start": start,
                    "end": end,
                    "cells": cells,
                })

            # 保留原课程，只追加 XLSX 中不存在的课程。
            for course in imported_courses:
                if course not in self.courses:
                    self.courses.append(course)

            self.rows.clear()
            for row in imported_rows:
                start = tk.StringVar(value=row["start"])
                end = tk.StringVar(value=row["end"])
                self.rows.append({
                    "start": start,
                    "end": end,
                    "cells": row["cells"],
                    "widgets": {},
                })
            self.render()
            logger.info("已导入 XLSX（尚未保存）: %s", file_path)
            messagebox.showinfo("导入成功", "课程表已导入当前编辑器，请检查后点击保存。", parent=self)
        except Exception as error:
            logger.exception("导入 XLSX 失败")
            messagebox.showerror("导入失败", str(error), parent=self)

    def save(self):
        self.sync_widgets()
        if not self.validate_data():
            logger.debug("因数据检查而阻止保存。")
            return False
        try:
            timetable = {"days": self.selected_days(), "rows": self.collect_rows()}
            save_class(self.prefix, timetable, self.courses)
            self.saved_state = self.current_state()
            messagebox.showinfo("保存成功", "课程表已保存到 data.zip。", parent=self)
            return True
        except OSError as error:
            messagebox.showerror("保存失败", str(error), parent=self)
            return False

    def validate_data(self):
        if not self.selected_days():
            messagebox.showerror("数据检查", "至少选择一天课程。", parent=self)
            return False
        for index, row in enumerate(self.rows, 1):
            for value in (row["start"].get(), row["end"].get()):
                try:
                    datetime.strptime(value, "%H:%M")
                except ValueError:
                    messagebox.showerror("数据检查", f"第 {index} 节时间必须为 HH:MM 格式。", parent=self)
                    return False
            start_hour, start_minute = map(int, row["start"].get().split(":", 1))
            end_hour, end_minute = map(int, row["end"].get().split(":", 1))
            start_total_minutes = 60 * start_hour + start_minute
            end_total_minutes = 60 * end_hour + end_minute
            if start_total_minutes >= end_total_minutes:
                messagebox.showerror("数据检查", f"第 {index} 节的开始时间必须早于结束时间。", parent=self)
                logger.debug("因数据检查而阻止保存。")
                return False
        return True

    def current_state(self):
        self.sync_widgets()
        return {
            "days": self.selected_days(),
            "rows": self.collect_rows(),
            "courses": list(self.courses),
        }

    def close(self):
        if self.current_state() != self.saved_state:
            logger.info("因未保存而阻止关闭。")
            choice = messagebox.askyesnocancel("未保存的修改", "课程表有未保存的修改，是否保存？", parent=self)
            if choice is None:
                return
            if choice and not self.save():
                return
        self.open_manager()

    def open_manager(self):
        self.destroy()
        self.manager.deiconify()
        self.manager.refresh()

    def edit_courses(self):
        dialog = tk.Toplevel(self)
        dialog.title("编辑课程")
        dialog.geometry("360x340")
        listbox = tk.Listbox(dialog, height=12)
        listbox.pack(fill="both", expand=True, padx=16, pady=16)
        for course in self.courses:
            listbox.insert(tk.END, course)

        def add():
            course = simpledialog.askstring("添加课程", "课程名称：", parent=dialog)
            if course and course not in self.courses:
                self.courses.append(course)
                listbox.insert(tk.END, course)
                self.render()

        def remove():
            selection = listbox.curselection()
            if selection:
                self.courses.pop(selection[0])
                listbox.delete(selection[0])
                self.render()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(buttons, text="添加", command=add).pack(side="left")
        ttk.Button(buttons, text="删除", command=remove).pack(side="left", padx=8)
        ttk.Button(buttons, text="完成", command=dialog.destroy).pack(side="right")


def start_editor(manager, prefix):
    manager.withdraw()
    TimetableEditor(manager, prefix)


def main():
    sync_thread = threading.Thread(
        target=sync_program.main,
        daemon=True,
        name="课程表同步程序",
    )
    sync_thread.start()
    root = tk.Tk()
    root.withdraw()
    manager = ClassManager(root, lambda prefix: start_editor(manager, prefix))
    root.mainloop()


if __name__ == "__main__":
    main()
