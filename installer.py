# -*- coding: utf-8 -*-
"""SmartCR 安装程序。"""

import shutil
import tkinter as tk
import tempfile
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_NAMES = {
    "admin": "教师端",
    "classroom": "教室端",
}


def payload_root():
    return Path(__file__).resolve().parent / "payload"


def extract_payload(package, destination):
    archive_path = payload_root() / f"{package}.zip"
    if not archive_path.is_file():
        raise FileNotFoundError(f"安装文件不存在：{archive_path}")
    temporary_path = Path(tempfile.mkdtemp(prefix="smart-cr-payload-"))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temporary_path)
        return temporary_path
    except (OSError, zipfile.BadZipFile):
        shutil.rmtree(temporary_path, ignore_errors=True)
        raise


def set_install_progress(value, text):
    progress_var.set(value)
    status_var.set(text)
    root.update_idletasks()


def install_packages(packages, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    total = max(len(packages), 1)
    for index, package in enumerate(packages, start=1):
        set_install_progress((index - 1) * 100 // total, f"正在安装 {APP_NAMES[package]}...")
        source = extract_payload(package, destination)
        target = destination / f"smart-cr-{APP_NAMES[package]}"
        try:
            shutil.copytree(source, target, dirs_exist_ok=True)
            if not any(target.rglob("*.exe")):
                raise FileNotFoundError(f"安装包 {APP_NAMES[package]} 中未找到可执行程序 (.exe)")
        finally:
            shutil.rmtree(source, ignore_errors=True)
        set_install_progress(index * 100 // total, f"{APP_NAMES[package]} 安装完成")


def choose_install(packages):
    destination = filedialog.askdirectory(title="选择安装位置", mustexist=False)
    if not destination:
        return
    for child in buttons.winfo_children():
        child.configure(state="disabled")
    set_install_progress(0, "开始安装...")
    try:
        install_packages(packages, destination)
    except (OSError, FileNotFoundError, ValueError) as error:
        set_install_progress(0, "安装失败")
        messagebox.showerror("安装失败", str(error), parent=root)
        for child in buttons.winfo_children():
            child.configure(state="normal")
        return
    set_install_progress(100, "安装完成")
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

progress_var = tk.IntVar(value=0)
status_var = tk.StringVar(value="等待安装")
progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100, length=280)
progress_bar.pack(fill="x", padx=24, pady=(0, 8))
status_label = tk.Label(root, textvariable=status_var, fg="#555555")
status_label.pack(fill="x", padx=24, pady=(0, 12))

context_menu = tk.Menu(root, tearoff=False)
context_menu.add_command(label="我全都装", command=lambda: choose_install(("admin", "classroom")))

root.mainloop()
