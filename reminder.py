"""提供可退出的定时全屏提醒。"""

import tkinter as tk
from datetime import datetime
from html import escape
from typing import Callable, Optional

from winrt.windows.data.xml.dom import XmlDocument
from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager


def _show_windows_toast(message: str) -> None:
	"""将提醒同步到 Windows 通知中心；通知不可用时不影响主窗口。"""
	try:
		xml = XmlDocument()
		xml.load_xml(
			'<toast><visual><binding template="ToastGeneric">'
			f'<text>课程表提醒</text><text>{escape(message)}</text>'
			"</binding></visual></toast>"
		)
		notifier = ToastNotificationManager.create_toast_notifier("SmartCR.CourseReminder")
		notifier.show(ToastNotification(xml))
	except Exception:
		return


def show_reminder(
	message: str,
	delay_seconds: float = 0,
	show_at: Optional[datetime] = None,
	on_confirm: Optional[Callable[[], None]] = None,
	on_details: Optional[Callable[[], None]] = None,
	on_close: Optional[Callable[[], None]] = None,
	auto_close_seconds: Optional[float] = None,
) -> None:
	"""显示全屏提醒，提供确定按钮和可选的详情按钮。"""
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

	def confirm_reminder() -> None:
		close_reminder()
		if on_confirm is not None:
			on_confirm()

	def show_details() -> None:
		try:
			if on_details is not None:
				on_details()
		finally:
			close_reminder()

	def display_reminder() -> None:
		nonlocal close_after_id
		root.deiconify()
		root.title("课程表提醒")
		root.configure(background="#0b1320")
		root.attributes("-fullscreen", True)
		root.attributes("-topmost", True)
		_show_windows_toast(message)
		if auto_close_seconds is not None:
			close_after_id = root.after(round(auto_close_seconds * 1000), close_reminder)

		outer_frame = tk.Frame(root, background="#0b1320")
		outer_frame.pack(expand=True, fill="both", padx=72, pady=72)

		card = tk.Frame(
			outer_frame,
			background="#f7f4ed",
			highlightbackground="#27364a",
			highlightthickness=1,
		)
		card.pack(expand=True, fill="both", padx=80, pady=48)

		accent = tk.Frame(card, background="#e08f4f", height=8)
		accent.pack(fill="x")

		content = tk.Frame(card, background="#f7f4ed")
		content.pack(expand=True, fill="both", padx=72, pady=56)

		tkicker = tk.Label(
			content,
			text="课程表提醒  /  REMINDER",
			background="#f7f4ed",
			foreground="#b36532",
			font=("Microsoft YaHei UI", 12, "bold"),
			anchor="w",
		)
		tkicker.pack(fill="x")

		separator = tk.Frame(content, background="#e6dfd3", height=1)
		separator.pack(fill="x", pady=(18, 36))

		label = tk.Label(
			content,
			text=message,
			background="#f7f4ed",
			foreground="#182536",
			font=("Microsoft YaHei UI", 32, "bold"),
			justify="center",
			wraplength=min(max(root.winfo_screenwidth() - 420, 420), 980),
		)
		label.pack(expand=True, fill="both")

		button_frame = tk.Frame(content, background="#f7f4ed")
		button_frame.pack(pady=(36, 0))

		confirm_button = tk.Button(
			button_frame,
			text="确定",
			command=confirm_reminder,
			font=("Microsoft YaHei UI", 15, "bold"),
			foreground="#ffffff",
			background="#167d78",
			activeforeground="#ffffff",
			activebackground="#126761",
			borderwidth=0,
			highlightthickness=0,
			padx=34,
			pady=12,
			cursor="hand2",
		)
		confirm_button.pack(side="left", padx=6)
		confirm_button.focus_set()

		if on_details is not None:
			details_button = tk.Button(
				button_frame,
				text="查看详情",
				command=show_details,
				font=("Microsoft YaHei UI", 15),
				foreground="#314256",
				background="#e9e4da",
				activeforeground="#182536",
				activebackground="#ddd5c8",
				borderwidth=0,
				highlightthickness=0,
				padx=28,
				pady=12,
				cursor="hand2",
			)
			details_button.pack(side="left", padx=6)

	root.bind("<Escape>", lambda _event: close_reminder())
	root.protocol("WM_DELETE_WINDOW", close_reminder)
	root.after(round(delay_seconds * 1000), display_reminder)
	root.mainloop()


if __name__ == "__main__":
	show_reminder(
		"请查看今日课程安排。",
		delay_seconds=5,
		auto_close_seconds=10,
		on_confirm=lambda: print("已确认提醒"),
		on_details=lambda: print("正在查看详情"),
		on_close=lambda: print("提醒已关闭"),
	)
