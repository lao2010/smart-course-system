# Smart CR

基于 Python 的智能课程表管理与同步工具，适用于 Windows。管理员可以维护多个班级的课程表，课堂设备端根据本机配置显示课程并提供上课提醒；运行中的实例会通过局域网自动发现并同步最新课程表。

## 功能

- 管理多个年级和班级。
- 手动编辑课程表、上课时间和启用日期。
- 从 `.xlsx` 或 `.xlsm` 文件导入课程表。
- 编辑课程名称，并支持全系统或当前班级调换日期。
- 课堂设备按配置读取对应班级，并显示课程提醒。
- 通过局域网广播发现节点，自动查询版本并下载最新课程表。
- 下载课程表后校验 ZIP 内容，再原子替换本地数据文件。
- 提供 GitHub Actions + Nuitka Windows 构建流程。

## 环境要求

- Windows
- Python 3.11、3.12 或 3.13
- 运行设备位于同一个局域网，并允许 UDP 广播和程序 HTTP 通信

## 本地运行

使用 [uv](https://docs.astral.sh/uv/)：

```powershell
uv sync
uv run python for_admin.py
```

课堂设备端运行：

```powershell
uv run python for_classroom_device.py
```

也可以先激活虚拟环境，再直接使用 Python：

```powershell
.\.venv\Scripts\Activate.ps1
python for_admin.py
```

首次运行课堂设备端时，如果项目根目录没有 `config.json`，程序会弹出配置向导。

## 配置

`config.json` 用于指定课堂设备对应的班级和设备名称：

```json
{
	"grade": 10,
	"class": 2,
	"device_name": "高1年级2班"
}
```

- `grade`：年级数字，例如 `10`。
- `class`：班级数字，例如 `2`。
- `device_name`：设备显示名称。

管理员端的数据保存在 `data/data.zip` 中。管理员保存课程表后，课堂设备端会在局域网内自动发现更新并同步。`data/data.zip` 属于运行数据，默认不会提交到 Git。

## 局域网同步说明

- 节点通过 UDP `1981` 端口广播发现信息。
- 每个实例的 HTTP 服务使用随机可用端口，并在发现广播中公布端口。
- 所有实例必须使用相同的认证密钥；默认密钥位于 `friend_finder.py` 的 `SECRET_KEY`。
- Windows 防火墙需要允许 Python 或编译后的程序进行局域网通信。
- 两个程序实例可以互相发现；如果某个节点已经退出，连接失败后会从本地缓存移除。

如果日志中出现 `WinError 10061`，表示目标 IP 和端口当前没有服务监听，常见原因是对端程序已退出、端口被防火墙拦截，或发现缓存中的节点尚未过期。确认对端程序正在运行且网络策略允许通信即可。

## 编译 Windows 程序

仓库中的 `.github/workflows/build-nuitka.yml` 会在推送或手动触发工作流时构建：

- `smart-cr-admin`：管理员端
- `smart-cr-classroom-device`：课堂设备端

构建使用 Python 3.12、`uv sync --locked` 和 Nuitka，生成的程序目录会作为 GitHub Actions artifact 上传。构建前会自动创建空的 `data` 目录，运行时需要由管理员端生成或准备课程表数据。

## 项目入口

| 文件 | 用途 |
| --- | --- |
| `for_admin.py` | 管理员端 GUI，编辑班级和课程表 |
| `for_classroom_device.py` | 课堂设备端，读取课程表并显示提醒 |
| `main.py` | 局域网发现、版本查询和数据同步 |
| `httpholder.py` | 提供 `/query` 和 `/download` HTTP 接口 |
| `friend_finder.py` | UDP 节点发现和请求认证 |
| `data/data.zip` | 课程表运行数据 |
| `log/smart-cr.log` | 日志文件 |

## 开发检查

```powershell
uv run python -m py_compile main.py friend_finder.py
```
