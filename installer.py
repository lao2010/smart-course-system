# -*- coding: utf-8 -*-
"""SmartCR 安装程序。"""

import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox


APP_NAMES = {
    "admin": "教师端",
    "classroom": "教室端",
}


def payload_root():
    return Path(__file__).resolve().parent / "payload"


def install_packages(packages, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    root = payload_root()
    for package in packages:
        source = root / package
        if not source.is_dir():
            raise FileNotFoundError(f"安装文件不存在：{source}")
        target = destination if len(packages) == 1 else destination / f"smart-cr-{APP_NAMES[package]}"
        shutil.copytree(source, target, dirs_exist_ok=True)


def choose_install(packages):
    destination = filedialog.askdirectory(title="选择安装位置", mustexist=False)
    if not destination:
        return
    try:
        install_packages(packages, destination)
    except OSError as error:
        messagebox.showerror("安装失败", str(error), parent=root)
        return
    messagebox.showinfo("安装完成", "程序已安装完成。", parent=root)
    root.destroy()


def show_context_menu(event):
    context_menu.tk_popup(event.x_root, event.y_root)


root = tk.Tk()
root.title("SmartCR 安装程序")
root.geometry("360x190")
root.resizable(False, False)
root.bind("<Button-3>", show_context_menu)

frame = tk.Frame(root, padx=32, pady=24)
frame.pack(expand=True, fill="both")
tk.Label(frame, text="请选择要安装的程序", font=("Microsoft YaHei UI", 14, "bold")).pack(pady=(0, 18))
buttons = tk.Frame(frame)
buttons.pack()
tk.Button(buttons, text="教师端", width=12, command=lambda: choose_install(("admin",))).pack(side="left", padx=6)
tk.Button(buttons, text="教室端", width=12, command=lambda: choose_install(("classroom",))).pack(side="left", padx=6)

context_menu = tk.Menu(root, tearoff=False)
context_menu.add_command(label="我全都装", command=lambda: choose_install(("admin", "classroom")))

root.mainloop()
