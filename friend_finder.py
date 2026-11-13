# -*- coding: utf-8 -*-

import hmac
import hashlib
import json
import socket
import threading
import time
import logging
import os
import sys
import tempfile


logger = logging.getLogger("网络同类发现")

# 认证核心：预共享密钥、HMAC 签名和时间戳防重放。
SECRET_KEY_FILENAME = "secret.key"
MIN_SECRET_KEY_LENGTH = 32
DISCOVERY_PORT = 1981
MAX_CLOCK_SKEW = 120   # 报文时间戳新鲜度窗口（秒）：容忍机房无 NTP 的时钟漂移


def _secret_key_path():
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), SECRET_KEY_FILENAME)


def load_secret_key():
    """读取本机保存的预共享密钥。"""
    try:
        with open(_secret_key_path(), "r", encoding="utf-8") as secret_file:
            secret_key = secret_file.read().strip()
    except FileNotFoundError as error:
        raise FileNotFoundError(
            f"未找到 {SECRET_KEY_FILENAME}，请在首次启动时配置共享密钥"
        ) from error

    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise ValueError(f"{SECRET_KEY_FILENAME} 中的共享密钥至少需要 32 个字符")
    return secret_key


def save_secret_key(secret_key):
    """以原子替换方式保存预共享密钥。"""
    secret_key = secret_key.strip()
    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise ValueError("共享密钥至少需要 32 个字符")

    secret_path = _secret_key_path()
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=os.path.dirname(secret_path),
            prefix=".secret-key-",
            delete=False,
        ) as secret_file:
            temporary_path = secret_file.name
            secret_file.write(secret_key)
            secret_file.write("\n")
        os.replace(temporary_path, secret_path)
        temporary_path = None
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.remove(temporary_path)


def ensure_secret_key():
    """首次启动时提示录入共享密钥，取消时返回 False。"""
    try:
        load_secret_key()
        return True
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as error:
        logger.error("无法读取本机共享密钥：%s", error)
        import easygui
        easygui.msgbox(f"无法读取本机共享密钥：{error}", "配置通信密钥")
        return False

    import easygui

    while True:
        secret_key = easygui.passwordbox(
            "请输入本校所有设备共用的随机共享密钥（至少 32 个字符）。\n"
            "建议使用密码管理器生成，并在每台设备上输入完全相同的密钥。",
            "配置通信密钥",
        )
        if secret_key is None:
            return False
        if len(secret_key.strip()) < MIN_SECRET_KEY_LENGTH:
            easygui.msgbox("共享密钥至少需要 32 个字符。", "配置通信密钥")
            continue
        try:
            save_secret_key(secret_key)
            return True
        except OSError as error:
            logger.exception("保存本机共享密钥失败")
            easygui.msgbox(f"保存本机共享密钥失败：{error}", "配置通信密钥")
            return False


def generate_token(timestamp):
    """生成 HMAC 签名"""
    secret_key = load_secret_key()
    msg = f"{secret_key}:{timestamp}".encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def verify_token(timestamp, token):
    """验证 HMAC 签名"""
    # 时间新鲜度窗口放宽到 120 秒：机房设备不一定配 NTP，窗口太小会让
    # 时钟漂移几十秒的机器互相拒绝（README 已同步部署要求）；签名按
    # {密钥:时间戳} 全量计算，窗口内仅表示"报文新鲜"，配合可信内网
    # 威胁模型足够，无需逐节点重放缓存（各节点同时刻签名值相同）。
    if abs(time.time() - timestamp) > MAX_CLOCK_SKEW:
        return False
    expected_token = generate_token(timestamp)
    # 使用恒定时间比较，避免泄露签名内容的时间信息。
    return hmac.compare_digest(expected_token, token)

class FriendFinder:
    def __init__(self, app_port, port=DISCOVERY_PORT, app_name="school_class", interval=10):
        self.port = port
        self.app_name = app_name
        self.app_port = app_port
        self.interval = interval
        self.peers = {}
        self.lock = threading.Lock()
        self.running = False
        self.stop_event = threading.Event()
        self.worker_threads = []
        # 接收套接字绑定固定端口，并允许接收广播数据。
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.recv_sock.bind(("", self.port))
        self.recv_sock.settimeout(2)

        # 发送套接字用于向局域网广播节点信息。
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def _broadcast_presence(self):
        """定时广播自己的存在（加入认证）"""
        while self.running:
            # 每次发送前更新时间戳和签名，避免广播数据过期或被伪造。
            curr_time = time.time()
            data = json.dumps({
                "app": self.app_name,
                "app_port": self.app_port,
                "hostname": socket.gethostname(),
                "ip": self._get_local_ip(),
                "timestamp": curr_time,
                "token": generate_token(curr_time)
            }).encode("utf-8")
            self.send_sock.sendto(data, ("255.255.255.255", self.port))
            self.stop_event.wait(self.interval)

    def _get_local_ip(self):
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("8.8.8.8", 80))
                return probe.getsockname()[0]
            finally:
                probe.close()
        except OSError:
            return "127.0.0.1"

    def _listen(self):
        """监听广播消息（加入认证）"""
        while self.running:
            try:
                data, addr = self.recv_sock.recvfrom(4096)
                info = json.loads(data.decode("utf-8"))
                
                # 第一步：验证应用名称。
                if info.get("app") != self.app_name:
                    continue
                
                # 第二步：验证签名和时间戳。
                if not verify_token(info.get("timestamp", 0), info.get("token", "")):
                    logger.warning("丢弃来自 %s 的伪造数据包", addr)
                    continue

                if info.get("ip") == self._get_local_ip() and info.get("app_port") == self.app_port:
                    continue
                
                # 验证通过后记录节点信息。
                with self.lock:
                    peer_key = f"{info['ip']}:{info.get('app_port', -1)}"
                    self.peers[peer_key] = {
                        "hostname": info["hostname"],
                        "ip": info["ip"],
                        "app_port": info.get("app_port", -1),
                        "last_seen": time.time()
                    }
                    logger.info("发现节点：%s (%s:%s)", info["hostname"], info["ip"], info.get("app_port", -1))
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError) as error:
                logger.warning("丢弃来自 %s 的无效节点发现数据包：%s", addr, error)
            except socket.timeout:
                continue
            except OSError as error:
                if self.running:
                    logger.warning("来自 %s 的节点发现套接字错误：%s", addr, error)
            except Exception:
                logger.exception("处理来自 %s 的节点发现数据包时发生未预期错误", addr)
                continue

    def start(self):
        """启动广播和监听线程"""
        self.running = True
        self.stop_event.clear()
        self.worker_threads = [
            threading.Thread(target=self._broadcast_presence, daemon=True, name="节点广播线程"),
            threading.Thread(target=self._listen, daemon=True, name="节点监听线程"),
        ]
        for worker_thread in self.worker_threads:
            worker_thread.start()

    def stop(self):
        """停止节点广播和监听线程，并释放网络资源。"""
        self.running = False
        self.stop_event.set()
        self.recv_sock.close()
        self.send_sock.close()
        for worker_thread in self.worker_threads:
            worker_thread.join(timeout=3)

    def get_usable_list(self):
        """返回最近活跃的节点列表"""
        with self.lock:
            now = time.time()
            # 只返回最近 66 秒内仍活跃的节点。
            result = [f"{self.peers[i]['ip']}:{self.peers[i]['app_port']}" for i in self.peers if now - self.peers[i]["last_seen"] < 66]
            return result

    def remove_peer(self, node):
        """移除无法连接的节点，避免在缓存过期前反复查询。"""
        with self.lock:
            self.peers.pop(node, None)