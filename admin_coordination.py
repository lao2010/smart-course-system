# -*- coding: utf-8 -*-
"""管理员协作协调层。

设计要点（2026-11-13 与李厚颉对齐）：
- 发现：独立 app_name="school-admin"、独立 UDP 端口 1982，不与教室端发现（smart-cr/1981）混表。
- 选主：成员集合 = 本机 + 活跃对端；主持人 = min(数值 IP, device_id)。
  * IP 必须数值比较（字符串比较 "10.0.0.9" > "10.0.0.10" 是经典陷阱）；
  * device_id 跨重启稳定（uuid 持久化），IP 只做首选键，DHCP 变化时以 id 打破平局；
  * 成员表由心跳（广播）维持，主持人失联即在下一轮评估中自动易主（故障转移）。
- 写收敛：主持人/独立模式本机落盘；成员把保存载荷 POST 给主持人（HMAC 签名），
  主持人统一升版本，其余成员靠既有同步服务自动拉回最新档，避免多管理员互相覆盖。
- 人数上限：8 人。第 9 个管理员提交保存时收到明确拒绝（不做静默丢弃）。
"""

import base64
import ipaddress
import json
import logging
import os
import threading
import time
import uuid
import zipfile

import requests

import zip_operator
from friend_finder import FriendFinder, generate_token, local_ip
from logging_setup import configure_logging

logger = logging.getLogger("管理员协作")

ADMIN_DISCOVERY_PORT = 1982
MAX_ADMINS = 8
SAVE_TIMEOUT = 10
# 设备标识持久化文件（入 .gitignore，机器内唯一即可）。
DEVICE_ID_FILENAME = os.path.join("data", "admin_device.id")
# 同步进程把 HTTP 端口写到这里，GUI 进程据此广播自己的可写端点。
SYNC_PORT_FILENAME = os.path.join("data", "sync_port.txt")

ROOT = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_PATH = os.path.join(ROOT, "data", "data.zip")

_coordinator = None


def auth_headers():
    """复用全局预共享密钥的 HMAC 认证头（与教室端同步链路同一把密钥）。"""
    timestamp = time.time()
    return {
        "X-Auth-Timestamp": str(timestamp),
        "X-Auth-Token": generate_token(timestamp),
    }


def _read_text_file(path):
    try:
        with open(os.path.join(ROOT, path), "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return ""


def _atomic_write_text(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    temporary = full + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(temporary, full)


def load_or_create_device_id():
    """读取本机稳定设备标识，首次运行生成 uuid4。"""
    existing = _read_text_file(DEVICE_ID_FILENAME)
    if existing:
        return existing
    device_id = uuid.uuid4().hex
    _atomic_write_text(DEVICE_ID_FILENAME, device_id)
    return device_id


def read_sync_port():
    """读取本机同步服务的 HTTP 端口（同步进程启动时写入）。"""
    raw = _read_text_file(SYNC_PORT_FILENAME)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _valid_archive_name(name):
    """归档名白名单校验：禁绝对路径与目录穿越。"""
    if not name or name.startswith("/") or "\\" in name:
        return False
    parts = name.split("/")
    return all(part not in ("", ".", "..") for part in parts)


def apply_admin_payload(payload):
    """主持人侧落盘：删前缀 → 写文件 → 最后升 data.json 版本（保证事务次序）。

    返回新版本号（float）。抛 ValueError/RuntimeException 时 HTTP 层转 400/500。
    """
    files = payload.get("files") or {}
    delete_prefixes = payload.get("delete_prefixes") or []
    if not files and not delete_prefixes:
        raise ValueError("载荷为空：既无文件也无删除前缀")

    for name in files:
        if not _valid_archive_name(name):
            raise ValueError(f"非法归档名：{name!r}")
    for prefix in delete_prefixes:
        if not prefix or not _valid_archive_name(prefix.rstrip("/")):
            raise ValueError(f"非法删除前缀：{prefix!r}")

    if not os.path.exists(ARCHIVE_PATH):
        # 首次协作保存兜底：zip_change_file 需要已有档才能工作，先建空 zip
        try:
            with zipfile.ZipFile(ARCHIVE_PATH, "w"):
                pass
        except OSError as error:
            raise RuntimeError(f"无法初始化空档案：{error}") from error
    for prefix in delete_prefixes:
        if not zip_operator.zip_remove_prefix(ARCHIVE_PATH, prefix):
            raise RuntimeError(f"删除 {prefix} 失败")

    for name, content_b64 in files.items():
        content = base64.b64decode(content_b64)
        if not zip_operator.zip_change_file(ARCHIVE_PATH, name, content):
            raise RuntimeError(f"写入 {name} 失败")

    # 版本号最后写：中途失败时教室端不会拉到"版本已升但内容缺失"的半成品。
    raw = zip_operator.zip_read(ARCHIVE_PATH, "data.json")
    archive_info = {}
    if raw:
        try:
            archive_info = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            archive_info = {}
    if not isinstance(archive_info, dict):
        archive_info = {}
    archive_info["version"] = time.time()
    if not zip_operator.zip_change_file(
        ARCHIVE_PATH, "data.json", json.dumps(archive_info, ensure_ascii=False, indent=2).encode("utf-8")
    ):
        raise RuntimeError("更新 data.json 版本失败")
    return archive_info["version"]


class AdminCoordinator:
    """管理员成员表与保存路由（运行在管理端 GUI 进程）。"""

    def __init__(self):
        self.device_id = load_or_create_device_id()
        self.lock = threading.Lock()
        self._cache = None          # 最近一次选主评估结果
        self._cache_time = 0.0
        self._capped_warned = False
        self.finder = FriendFinder(
            app_port=read_sync_port(),
            port=ADMIN_DISCOVERY_PORT,
            app_name="school-admin",
            interval=5,
            device_id=self.device_id,
        )
        self.finder.start()
        # 同步进程每次重启端口都会变：广播线程读取的是定格的 self.app_port，
        # 这里用小循环持续把最新端口刷进去（读 sync_port.txt，文件缺失时置 0 退出候选）。
        threading.Thread(target=self._refresh_port_loop, daemon=True).start()

    def _refresh_port_loop(self):
        while self.finder.running:
            self.finder.app_port = read_sync_port()
            self.finder.stop_event.wait(5)

    # ---- 成员与选主 ----

    def _candidates(self):
        """候选主持人列表 [(ip_int, device_id, ip, app_port)]。"""
        candidates = []
        my_port = read_sync_port()
        if my_port > 0:
            candidates.append((int(ipaddress.ip_address(local_ip())), self.device_id, local_ip(), my_port))
        for peer in self.finder.alive_peers(max_age=3 * self.finder.interval):
            if peer.get("app_port", -1) > 0:
                peer_id = peer.get("id") or f"{peer.get('hostname')}@{peer.get('ip')}"
                candidates.append((int(ipaddress.ip_address(peer["ip"])), peer_id, peer["ip"], peer["app_port"]))
        return candidates

    def _evaluate(self, max_age_seconds=2.0):
        """带短缓存的选主评估。返回 dict：am_host/host/members/solo/capped。"""
        with self.lock:
            now = time.time()
            if self._cache is not None and now - self._cache_time < max_age_seconds:
                return self._cache
            candidates = self._candidates()
            members = len(candidates)
            solo = not candidates
            if solo:
                # 本机同步服务未运行：只写本机档（不广播端点，他人不会选我），
                # 语义上仍是"主持人模式"，只是无人协作。
                result = {"am_host": True, "host": None, "members": 1, "solo": True, "capped": False}
            else:
                # 选主：min(数值 IP, device_id)，稳定 id 打破平局
                winner = min(candidates)
                result = {
                    "am_host": winner[1] == self.device_id,
                    "host": (winner[2], winner[3]),
                    "members": members,
                    "solo": False,
                    "capped": members > MAX_ADMINS,
                }
            self._cache = result
            self._cache_time = now
            if result["capped"] and not self._capped_warned:
                self._capped_warned = True
                logger.warning("在线管理员已达 %d 人上限（当前 %d 人）", MAX_ADMINS, members)
            return result

    def refresh(self):
        with self.lock:
            self._cache = None
            self._cache_time = 0.0

    def state(self, max_age_seconds=30):
        """公共入口：返回最近一次（或强制重评的）选主状态。"""
        return self._evaluate(max_age_seconds=max_age_seconds)

    # ---- 保存路由 ----

    def submit(self, files, delete_prefixes=None):
        """统一保存出口。返回状态消息字符串；失败抛 RuntimeError。

        - 主持人 / 独立模式：返回 "local"，由调用方本机落盘；
        - 成员：转发主持人，由主持人统一落盘升版本。
        """
        state = self._evaluate()
        if state["capped"]:
            raise RuntimeError(f"在线管理员已达 {MAX_ADMINS} 人上限，无法加入协作")
        if state["am_host"]:
            return "local"

        host_ip, host_port = state["host"]
        payload = {
            "files": {name: base64.b64encode(content).decode("ascii") for name, content in files.items()},
            "delete_prefixes": list(delete_prefixes or []),
            "sender": local_ip(),
        }
        url = f"http://{host_ip}:{host_port}/admin/save"
        try:
            response = requests.post(url, json=payload, headers=auth_headers(), timeout=SAVE_TIMEOUT)
        except requests.RequestException as error:
            self.refresh()
            raise RuntimeError(
                f"无法联系主持人 {host_ip}:{host_port}（{error}）。"
                "已重新评估角色，请重试；若本机已升为主持人将直接本机保存。"
            ) from error
        if response.status_code == 200:
            return f"已提交主持人 {host_ip}，新版本已同步下发（{response.text.strip()}）"
        # 主持人明确拒绝（密钥不符 / 上限 / 载荷非法）
        raise RuntimeError(f"主持人拒绝保存（HTTP {response.status_code}）：{response.text.strip()}")

    def status_text(self):
        state = self._evaluate()
        if state["solo"]:
            return "独立模式（同步服务未运行，仅本机保存）"
        if state["capped"]:
            return f"⚠ 协作超员：{state['members']} 人（上限 {MAX_ADMINS}）"
        if state["am_host"]:
            return f"主持人（在线管理员 {state['members']} 人）"
        return f"成员 → 主持人 {state['host'][0]}（在线 {state['members']} 人）"


def start_coordinator():
    """启动全局协调器；密钥未配置时降级为"不可用"状态，不阻塞 GUI。"""
    global _coordinator
    if _coordinator is not None:
        return _coordinator
    try:
        generate_token(time.time())  # 触发密钥存在性检查
        _coordinator = AdminCoordinator()
    except (FileNotFoundError, ValueError) as error:
        logger.warning("管理员协作未启用：%s", error)
    return _coordinator


def get_coordinator():
    return _coordinator


def coordinator_status():
    if _coordinator is None:
        return "协作未启用（共享密钥未配置）"
    try:
        return _coordinator.status_text()
    except (OSError, ValueError) as error:
        return f"协作状态异常：{error}"


if __name__ == "__main__":
    configure_logging()
    started = start_coordinator()
    if started:
        logger.info("本机设备标识：%s", started.device_id)
        logger.info("协作状态：%s", coordinator_status())
    else:
        logger.info("协作未启用")
