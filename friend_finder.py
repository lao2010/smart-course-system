import hmac
import hashlib
import json
import socket
import threading
import time
import logging


logger = logging.getLogger(__name__)

# 认证核心：预共享密钥、HMAC 签名和时间戳防重放。
SECRET_KEY = "2026_Secret:lkjinnhbgsdjcn123456789"  # 所有运行该程序的电脑必须使用相同密钥。
DISCOVERY_PORT = 1981

def generate_token(timestamp):
    """生成 HMAC 签名"""
    msg = f"{SECRET_KEY}:{timestamp}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()

def verify_token(timestamp, token):
    """验证 HMAC 签名"""
    # 只接受时间偏差不超过 10 秒的消息，避免旧消息被重复利用。
    if abs(time.time() - timestamp) > 10:
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
            time.sleep(self.interval)

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
        threading.Thread(target=self._broadcast_presence, daemon=True).start()
        threading.Thread(target=self._listen, daemon=True).start()

    def get_usable_list(self):
        """返回最近活跃的节点列表"""
        with self.lock:
            now = time.time()
            # 只返回最近 66 秒内仍活跃的节点。
            result = [f"{self.peers[i]['ip']}:{self.peers[i]['app_port']}" for i in self.peers if now - self.peers[i]["last_seen"] < 66]
            return result