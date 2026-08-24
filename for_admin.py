"""课程表管理器入口。"""

import json
import logging
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from zipfile import ZipFile

from zip_operator import zip_change_file


logging.basicConfig(level=logging.INFO)
ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_PATH = os.path.join(ROOT, "data", "data.zip")
DAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def class_prefix(grade, class_number):
    return f"g{grade}-c{class_number}"


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


def load_json(path, default):
    with ZipFile(ARCHIVE_PATH) as archive:
        try:
            with archive.open(path) as stream:
                return json.loads(stream.read().decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return default


def save_class(prefix, timetable, courses):
    ensure_archive()
    payloads = {
        f"{prefix}/timetable.json": json.dumps(timetable, ensure_ascii=False, indent=2).encode("utf-8"),
        f"{prefix}/courses.json": json.dumps(courses, ensure_ascii=False, indent=2).encode("utf-8"),
    }
    for path, content in payloads.items():
        if not zip_change_file(ARCHIVE_PATH, path, content):
            raise OSError(f"无法写入 {path}")


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
        self.listbox = tk.Listbox(self, height=11, activestyle="dotbox")
        self.listbox.pack(fill="both", expand=True, padx=24)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.select())
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=24, pady=16)
        ttk.Button(buttons, text="添加班级", command=self.add).pack(side="left")
        ttk.Button(buttons, text="删除班级", command=self.remove).pack(side="left", padx=8)
        ttk.Button(buttons, text="打开", command=self.select).pack(side="right")
        self.refresh()

    def refresh(self):
        self.listbox.delete(0, tk.END)
        for prefix in available_classes():
            self.listbox.insert(tk.END, prefix)

    def add(self):
        grade = simpledialog.askstring("添加班级", "年级：", parent=self)
        class_number = simpledialog.askstring("添加班级", "班级：", parent=self)
        if not grade or not class_number:
            return
        prefix = class_prefix(grade.strip(), class_number.strip())
        if prefix in available_classes():
            messagebox.showinfo("提示", "该班级已经存在。", parent=self)
            return
        save_class(prefix, {"days": [0, 1, 2, 3, 4], "rows": []}, [])
        self.refresh()

    def remove(self):
        selection = self.listbox.curselection()
        if not selection:
            return
        prefix = self.listbox.get(selection[0])
        if messagebox.askyesno("确认删除", f"确定删除 {prefix} 吗？", parent=self):
            delete_class(prefix)
            self.refresh()

    def select(self):
        selection = self.listbox.curselection()
        if selection:
            self.on_select(self.listbox.get(selection[0]))


class TimetableEditor(tk.Toplevel):
    def __init__(self, manager, prefix):
        super().__init__(manager)
        self.manager = manager
        self.prefix = prefix
        self.title(f"课程表编辑器 - {prefix}")
        self.geometry("1050x620")
        self.minsize(760, 480)
        self.rows = []
        self.courses = load_json(f"{prefix}/courses.json", [])
        timetable = load_json(f"{prefix}/timetable.json", {"days": [0, 1, 2, 3, 4], "rows": []})
        self.day_vars = [tk.BooleanVar(value=index in timetable.get("days", [])) for index in range(7)]

        self.make_toolbar()
        self.make_day_selector()
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for row in timetable.get("rows", []):
            self.add_row(row)
        if not self.rows:
            self.add_row()

    def make_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=16, pady=12)
        ttk.Label(toolbar, text=f"班级：{self.prefix}", font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        ttk.Button(toolbar, text="增加节次", command=self.add_period).pack(side="left", padx=(24, 0))
        ttk.Button(toolbar, text="删除末节", command=self.remove_period).pack(side="left", padx=8)
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
        days = self.selected_days()
        ttk.Label(self.grid_frame, text="时间").grid(row=0, column=0, sticky="nsew", padx=3, pady=3)
        for column, day in enumerate(days, 1):
            ttk.Label(self.grid_frame, text=DAY_NAMES[day], anchor="center").grid(row=0, column=column, sticky="nsew", padx=3, pady=3)
        for row_index, row in enumerate(self.rows, 1):
            time_frame = ttk.Frame(self.grid_frame)
            time_frame.grid(row=row_index, column=0, sticky="nsew", padx=3, pady=3)
            row["start_entry"] = ttk.Entry(time_frame, width=8)
            row["end_entry"] = ttk.Entry(time_frame, width=8)
            row["start_entry"].insert(0, row["start"].get())
            row["end_entry"].insert(0, row["end"].get())
            row["start_entry"].pack()
            row["end_entry"].pack(pady=(3, 0))
            for column, day in enumerate(days, 1):
                combo = ttk.Combobox(self.grid_frame, values=self.courses, state="readonly", width=18)
                combo.set(row["cells"].get(str(day), ""))
                combo.grid(row=row_index, column=column, sticky="ew", padx=3, pady=3)
                row["widgets"][day] = combo
        for column in range(len(days) + 1):
            self.grid_frame.columnconfigure(column, weight=1)

    def add_row(self, data=None):
        data = data or {"start": "", "end": "", "cells": {}}
        start = tk.StringVar(value=data.get("start", ""))
        end = tk.StringVar(value=data.get("end", ""))
        self.rows.append({"start": start, "end": end, "cells": data.get("cells", {}), "widgets": {}})
        self.render()

    def sync_widgets(self):
        for row in self.rows:
            if "start_entry" in row:
                row["start"].set(row["start_entry"].get().strip())
                row["end"].set(row["end_entry"].get().strip())
            for day, widget in row["widgets"].items():
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

    def save(self):
        try:
            save_class(self.prefix, {"days": self.selected_days(), "rows": self.collect_rows()}, self.courses)
            messagebox.showinfo("保存成功", "课程表已保存到 data.zip。", parent=self)
        except OSError as error:
            messagebox.showerror("保存失败", str(error), parent=self)

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
    root = tk.Tk()
    root.withdraw()
    manager = ClassManager(root, lambda prefix: start_editor(manager, prefix))
    root.mainloop()


if __name__ == "__main__":
    main()
