"""提供可退出的定时全屏提醒。"""

import tkinter as tk
from datetime import datetime
from typing import Callable, Optional


def show_reminder(
	message: str,
	delay_seconds: float = 0,
	show_at: Optional[datetime] = None,
	on_close: Optional[Callable[[], None]] = None,
	auto_close_seconds: Optional[float] = None,
) -> None:
	"""在指定时间显示全屏提醒，并支持关闭回调和自动关闭。"""
	if not message:
		raise ValueError("提醒内容不能为空")
	if delay_seconds < 0:
		raise ValueError("延迟时间不能小于 0")
	if auto_close_seconds is not None and auto_close_seconds < 0:
		raise ValueError("自动关闭时间不能小于 0")

	root = tk.Tk()
	root.withdraw()
	closed = False
	close_after_id: Optional[str] = None

	if show_at is not None:
		delay_seconds = max((show_at - datetime.now()).total_seconds(), 0)

	def close_reminder() -> None:
		nonlocal closed
		if closed:
			return
		closed = True
		if close_after_id is not None:
			root.after_cancel(close_after_id)
		root.destroy()
		if on_close is not None:
			on_close()

	def display_reminder() -> None:
		nonlocal close_after_id
		root.deiconify()
		root.title("课程表提醒")
		root.configure(background="#101820")
		root.attributes("-fullscreen", True)
		root.attributes("-topmost", True)
		if auto_close_seconds is not None:
			close_after_id = root.after(round(auto_close_seconds * 1000), close_reminder)

		frame = tk.Frame(root, background="#101820")
		frame.pack(expand=True, fill="both", padx=48, pady=48)

		label = tk.Label(
			frame,
			text=message,
			background="#101820",
			foreground="#f5f7fa",
			font=("Microsoft YaHei UI", 36, "bold"),
			justify="center",
			wraplength=1200,
		)
		label.pack(expand=True)

		close_button = tk.Button(
			frame,
			text="关闭提醒",
			command=close_reminder,
			font=("Microsoft YaHei UI", 16),
			padx=24,
			pady=10,
		)
		close_button.pack(pady=(0, 24))
		close_button.focus_set()

	root.bind("<Escape>", lambda _event: close_reminder())
	root.protocol("WM_DELETE_WINDOW", close_reminder)
	root.after(round(delay_seconds * 1000), display_reminder)
	root.mainloop()


if __name__ == "__main__":
	show_reminder(
		"请查看今日课程安排。",
		delay_seconds=5,
		auto_close_seconds=10,
		on_close=lambda: print("提醒已关闭"),
	)
