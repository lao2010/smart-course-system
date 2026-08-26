# -*- coding: utf-8 -*-
"""SmartCR 卸载程序。"""

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


install_root = Path(__file__).resolve().parent


def uninstall():
    if not messagebox.askyesno("确认卸载", "确定卸载当前 SmartCR 程序吗？", parent=root):
        return
    command = f'timeout /t 2 /nobreak >nul & rmdir /s /q "{install_root}"'
    try:
        subprocess.Popen(["cmd", "/c", command], creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError as error:
        messagebox.showerror("卸载失败", str(error), parent=root)
        return
    root.destroy()


root = tk.Tk()
root.title("SmartCR 卸载程序")
root.geometry("320x140")
root.resizable(False, False)
tk.Label(root, text="确定要卸载 SmartCR 吗？", font=("Microsoft YaHei UI", 13)).pack(pady=(28, 18))
tk.Button(root, text="卸载", width=12, command=uninstall).pack()
root.mainloop()
