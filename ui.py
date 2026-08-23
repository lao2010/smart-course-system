"""Launch the WinUI 3 desktop client for smart-cr.

The actual native UI lives in winui3/ because WinUI 3 is a .NET Windows App SDK
framework rather than a Python UI toolkit.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PROJECT_FILE = PROJECT_ROOT / "winui3" / "SmartCr.WinUI.csproj"


def main() -> int:
	if platform.system() != "Windows":
		print("WinUI 3 客户端只能在 Windows 上运行。", file=sys.stderr)
		return 1

	dotnet = shutil.which("dotnet")
	if dotnet is None:
		print("未找到 dotnet。请安装 .NET 8 SDK: https://dotnet.microsoft.com/download/dotnet/8.0", file=sys.stderr)
		return 1
	if not _has_dotnet8_sdk(dotnet):
		print("需要 .NET 8 或更高版本的 SDK（dotnet --list-sdks 可查看已装版本）。", file=sys.stderr)
		return 1
	if not PROJECT_FILE.is_file():
		print(f"WinUI 3 项目不存在: {PROJECT_FILE}", file=sys.stderr)
		return 1

	print("正在构建并启动 WinUI 3 客户端（首次构建可能较慢）...", file=sys.stderr)
	return subprocess.call(
		[dotnet, "run", "--project", str(PROJECT_FILE), "--"] + sys.argv[1:],
		cwd=PROJECT_ROOT,
	)


def _has_dotnet8_sdk(dotnet: str) -> bool:
	result = subprocess.run(
		[dotnet, "--list-sdks"],
		capture_output=True,
		text=True,
		check=False,
	)
	if result.returncode != 0:
		return False
	return any(
		line.split(" ", 1)[0].split(".")[0].isdigit() and int(line.split(" ", 1)[0].split(".")[0]) >= 8
		for line in result.stdout.splitlines()
	)


if __name__ == "__main__":
	raise SystemExit(main())
