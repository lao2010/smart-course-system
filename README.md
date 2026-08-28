<h1 align="center">Smart Course System · 智能课程表同步与课堂提醒</h1>
<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python"></a>
  <a href="#"><img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="Platform"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
</p>

> 无需服务器、无需公网 IP：教室电脑在局域网内自动组网、自动同步最新课程表，并在每节课上课前弹出全屏提醒。

---

## 📌 这是什么？

**Smart Course System** 是一套面向中学教室场景的轻量级课程表系统，由两个角色组成：

| 角色 | 程序 | 使用者 | 职责 |
| --- | --- | --- | --- |
| 管理端 | `for_admin.py` | 教师 / 电教管理员 | 维护班级列表、编辑课程表、从 Excel 导入 |
| 教室端 | `for_classroom_device.py` | 教室一体机 / 学生机 | 接收提醒弹窗、展示课表详情 |

两端各自内置同一个「数据同步服务」（`main.py`）：通过 UDP 广播自动发现同一局域网内的其他设备，互查版本号，一旦发现更新的课程表数据就自动下载替换——**管理员在一台电脑上点「保存」，几十秒内全楼教室的课表即为最新**。
<!-- 建议在这里插入一张架构图或运行截图
<p align="center">
  <img src="docs/architecture.png" width="760" alt="系统架构">
</p>
-->

## ✨ 功能特性
- **⏰ 准时全屏提醒** — 每节课上课分钟触发置顶全屏窗口，支持「确定」「查看详情」，超时自动关闭；同时推送 Windows 系统通知（Toast）。
- **📊 可视化排课** — 图形界面增删班级、增删节次、勾选启用星期（可不连续）、课程下拉框填写，所见即所得。
- **📥 Excel 课程表导入** — 自动定位表头，识别横向合并（午休、眼保健操等全天活动）、纵向合并（连堂课）、全角冒号与多种时间写法。
- **🌐 零配置局域网同步** — UDP 广播发现节点 → 多线程并发查询版本 → 校验压缩包完整性后原子替换本地 `data.zip`，中途断电也不会损坏数据。
- **🔐 通信认证** — 所有节点使用预共享密钥进行 HMAC-SHA256 签名，时间戳防重放，伪造/过期报文一律丢弃。
- **🚦 过载保护** — HTTP 服务端使用信号量限流，超过并发上限时直接返回「服务器繁忙」，避免被拖垮。
- **📝 双通道日志** — 控制台与 `log/smart-cr.log` 同时记录运行状态，方便排查问题。

## 🗂 项目结构

```text
smart-course-system/
├── for_admin.py             # 管理端入口：班级管理 + 课程表编辑器
├── for_classroom_device.py  # 教室端入口：配置向导 + 提醒主循环
├── main.py                  # 数据同步服务（两端共用）：发现节点、比对版本、下载数据
├── friend_finder.py         # UDP 局域网节点发现 + HMAC 认证
├── httpholder.py            # 轻量 HTTP 服务：/query 查询版本，/download 下载课表包
├── get_course_from_xlsx.py  # Excel 课程表解析器（合并单元格识别）
├── zip_operator.py          # data.zip 读取 / 校验 / 替换工具
├── version_query.py         # 从 data.zip 中查询当前数据版本
├── json_operator.py         # JSON 配置读写工具
├── gui.py                   # 全屏提醒窗口 + Windows Toast
├── logging_setup.py         # 日志初始化
├── pyproject.toml           # 项目元数据
├── uv.lock                  # uv 锁定的完整依赖清单
├── requirements.txt         # pip 用户的精简依赖清单
├── data/
│   └── data.zip             # 全部业务数据存放于此
└── config.json              # 教室端首次运行时生成的本机配置
```

### `data.zip` 内部结构

```text
data.zip
├── data.json                      # {"version": 1730000000.0} 保存时间戳即版本号
├── classes.json                   # {"g10-c3": "高一(3)班", ...}
├── courses.json                   # ["数学", "语文", ...]
└── g10-c3/
    └── timetable.json             # 对应班级的课程表
```

### 课程表格式示例

```json
{
  "days": [0, 1, 2, 3, 4],
  "rows": [
    {
      "start": "08:00",
      "end": "08:45",
      "cells": { "0": "数学", "1": "语文", "2": "英语" }
    },
    {
      "start": "08:55",
      "end": "09:40",
      "cells": { "0": "语文", "1": "数学", "2": "物理" }
    }
  ]
}
```

- `days`：启用的星期，`0` 表示周一，`6` 表示周日；
- `rows.cells` 的键为星期索引字符串，留空表示该天此节无课。

## 🖥 运行环境

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10/11（Toast 通知依赖）；核心同步逻辑理论上可在 Linux/macOS 运行 |
| Python | 3.10 及以上（推荐使用 uv 管理） |
| 网络 | 同一局域网内互通，放行 UDP 1981 与随机分配的 TCP 端口 |

## 📦 安装

### 方式一：uv（推荐）

```bash
git clone https://github.com/lao2010/smart-course-system.git
cd smart-course-system
uv sync                 # 自动创建虚拟环境并按 uv.lock 安装全部依赖
uv run python for_admin.py    # 直接运行任意脚本，无需手动激活
```

### 方式二：pip

```bash
git clone https://github.com/lao2010/smart-course-system.git
cd smart-course-system
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python for_admin.py
```

## 🚀 快速开始

### ① 在教师机上启动管理端

```bash
python for_admin.py
```
1. 点击「添加班级」，输入年级与班号（例如 10 年级 3 班 → 内部前缀 `g10-c3`）；
2. 双击班级进入「课程表编辑器」：
   - 「增加节次 / 删除末节」调整每节课的时间段；
   - 勾选该课表在周几生效；
   - 点「编辑课程」维护课程名候选列表；
   - 点「导入 XLSX」一键解析现成 Excel 课表；
   - 检查无误后点「保存」——此时 `data.json` 的版本号更新为当前时间戳。
3. 管理端同时后台运行同步服务，教室机会自动收到新版本。

### ② 在教室电脑上启动客户端

```bash
python for_classroom_device.py
```
- 首次运行会出现「配置向导」：依次输入年级、班级、设备名称，保存在本目录 `config.json`；
- 之后每一节有课的开始分钟，屏幕将弹出全屏提醒（约延迟 5 秒出现、10 秒无操作自动关闭），并同步发送一条系统通知；
- 若需更换绑定班级，删除 `config.json` 后重启程序即可重新向导配置。

### ③ 数据如何流转

```text
管理端保存 (version 变大)
        │
        ▼  UDP:1981 广播（HMAC 签名）
所有设备互相发现 ←——————————→ 互发 /query 比较版本
        │                          │ 发现更高版本
        ▼                          ▼
管理端同时开放 /download ←——— 教室端下载 → 校验 zip → 原子替换 data.zip
                                   │
                                   ▼
                        教室端 ≤20 秒后读到新课表
```

## ⚙️ 高级选项

| 场景 | 操作方式 |
| --- | --- |
| 手动指定监听端口 | `python main.py --host 0.0.0.0 --port 8000` |
| 限制最大并发下载 | `python main.py --max-concurrent 5`（默认 2） |
| 更换共享密钥 | 编辑 `friend_finder.py` 中的 `SECRET_KEY`，所有设备必须一致 |
| 全系统调课 | 管理端「全系统调换日期」一次性交换全部班级某两天的内容（如临时调休） |

## 🔐 安全说明

- 所有发现与请求报文均携带 `HMAC-SHA256(timestamp)` 签名，时间偏差超过 10 秒即视为过期丢弃；
- 校验使用恒定时间比较，防止通过耗时侧信道探测签名；
- 报文主体未加密，请仅在可信校园内网部署，不要映射到公网。

## ❓ 常见问题

### 两台机器始终互相发现不了？

按顺序排查：① 是否在同一网段且路由器未开启 AP 隔离；② 防火墙是否放行 UDP 1981 与程序 TCP 端口；③ 各设备的 `SECRET_KEY` 是否一致；④ 设备间系统时间偏差是否小于 10 秒。

### 为什么我的修改没有同步到教室？

只有点击管理端的「保存」才会提升 `data.json` 中的版本号；未保存的编辑不会广播。确认保存后再等待一个同步周期（通常不超过 60 秒）。

### 错过了某节课的提醒会补弹吗？

不会。客户端对每个开始时间只提醒一次，避免在课前堆积重复弹窗；重启程序也不会回溯当天已过去的时间点。

### Toast 通知没有显示？

确认系统「设置 → 系统 → 通知」中允许应用通知；非 Windows 平台将自动跳过 Toast，不影响全屏窗口提醒。

### Excel 导入失败的常见原因？

表格中必须存在同时包含「节次/时段/时间」关键词和星期关键词的表头行；纯图片课表无法解析。

## 🗺 Roadmap

- [x] Nuitka 一键打包为 exe，学校电脑无需安装 Python
- [ ] `data.zip` 加密存储
- [ ] Web 管理面板，支持手机远程调课
- [ ] 考试倒计时、眼保健操音效自定义
- [ ] Linux/macOS 桌面提醒适配

## 🤝 参与贡献

欢迎提交 Issue 与 Pull Request！为保证风格统一，请注意：
1. 中文注释与日志为主，函数均带 docstring；
2. 提交前运行一遍管理端与教室端手动回归测试；
3. 单个 PR 聚焦一件事，便于 review。

## 📄 许可证

本项目基于 [MIT License](./LICENSE) 发布——允许任何人在保留版权声明的前提下自由使用、修改和分发（包括商用）。
若未来希望限制闭源商用，可考虑迁移到 GPL-3.0 并提前告知现有使用者，选择参考 [choosealicense.com](https://choosealicense.com/)。

## 💬 联系与反馈

提交 Issue：
<https://github.com/lao2010/smart-course-system/issues>

---
<p align="center">如果这个项目帮到了你们班，欢迎点一个 ⭐ Star 支持开发！</p>
