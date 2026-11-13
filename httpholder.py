# -*- coding: utf-8 -*-
"""提供数据下载和版本查询接口的轻量级 HTTP 服务。"""

import importlib.util
import json
import mimetypes
import version_query
import random
import os
import threading
import logging
from friend_finder import verify_token, local_ip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from logging_setup import configure_logging


ROOT = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger("HTTP-数据同步响应服务")

# admin 角色门控：仅管理端的同步进程（--role admin）接受 /admin/save，
# 教室端一律 403，避免普通教室机变成可写节点。
allow_admin_routes = False
# /admin/save 载荷上限（课程表 JSON 很小，32MB 已远超需求）。
MAX_ADMIN_SAVE_BODY = 32 * 1024 * 1024
# 回环来源判定（测试单机仿真时可替换）。
LOOPBACK_IPS = ("127.0.0.1", "::1")


class Handler(BaseHTTPRequestHandler):
        def _authorized(self):
                timestamp = self.headers.get("X-Auth-Timestamp")
                token = self.headers.get("X-Auth-Token")
                try:
                        return timestamp is not None and verify_token(float(timestamp), token or "")
                except (TypeError, ValueError):
                        return False

        def _send(self, status, body, content_type="text/plain; charset=utf-8"):
                if isinstance(body, str):
                        body = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def do_GET(self):
                if not self.server.request_slots.acquire(blocking=False):
                        self._send(500, "服务器繁忙")
                        return
                try:
                        self._do_get()
                finally:
                        self.server.request_slots.release()

        def _do_get(self):
                """响应拉取课程表数据行为"""
                if not self._authorized():
                        self._send(401, "未授权")
                        return
                request = urlparse(self.path)
                if request.path == "/download":
                        path = os.path.join(ROOT, "data", "data.zip")
                        if not os.path.isfile(path):
                                self._send(404, "未找到 data/data.zip")
                                return
                        with open(path, "rb") as stream:
                                body = stream.read()
                        self.send_response(200)
                        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
                        self.send_header("Content-Disposition", 'attachment; filename="data.zip"')
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return

                if request.path == "/query":
                        try:
                                result = version_query.get_version()
                                self._send(200, str(result))
                        except (AttributeError, TypeError, ValueError) as exc:
                                self._send(400, str(exc))
                        except Exception as exc:
                                self._send(500, str(exc))
                        return

                self._send(404, "未找到请求的资源")

        def do_POST(self):
                if not self.server.request_slots.acquire(blocking=False):
                        self._send(500, "服务器繁忙")
                        return
                try:
                        self._do_post()
                finally:
                        self.server.request_slots.release()

        def _do_post(self):
                """管理员协作保存接口：成员管理员把保存载荷提交给主持人落盘。"""
                request = urlparse(self.path)
                if request.path != "/admin/save":
                        self._send(404, "未找到请求的资源")
                        return
                if not allow_admin_routes:
                        self._send(403, "本机不是管理端同步进程，拒绝协作写入")
                        return
                if not self._authorized():
                        self._send(401, "未授权")
                        return
                # 拒绝本机来源：管理员 GUI 只应把载荷发给别人，本机保存走本地路径，
                # 若回环打到自己也落盘会导致版本双重提升。
                sender_ip = self.client_address[0]
                if sender_ip in LOOPBACK_IPS or sender_ip == local_ip():
                        self._send(403, "本机保存请走本地路径，勿经协作接口回环")
                        return
                try:
                        length = int(self.headers.get("Content-Length", 0))
                except ValueError:
                        self._send(400, "Content-Length 非法")
                        return
                if length <= 0 or length > MAX_ADMIN_SAVE_BODY:
                        self._send(400, "载荷大小非法")
                        return
                try:
                        payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                        self._send(400, "载荷不是合法 JSON")
                        return
                try:
                        import admin_coordination
                        new_version = admin_coordination.apply_admin_payload(payload)
                except ValueError as exc:
                        self._send(400, str(exc))
                        return
                except (OSError, RuntimeError, KeyError, TypeError) as exc:
                        logger.exception("协作保存落盘失败（来源 %s）", sender_ip)
                        self._send(500, f"落盘失败：{exc}")
                        return
                logger.info("管理员 %s 的协作保存已落盘，新版本 %s", sender_ip, new_version)
                self._send(200, f"新版本 {new_version:.3f}")

        def log_message(self, format, *args):
                logger.info("HTTP %s - %s", self.address_string(), format % args)


class LoadSheddingHTTPServer(ThreadingHTTPServer):
        def __init__(self, server_address, handler_class, max_concurrent):
                super().__init__(server_address, handler_class)
                self.request_slots = threading.BoundedSemaphore(max_concurrent)
port = 0
ready_event = threading.Event()
server_instance = None
def main():
        global port, server_instance
        configure_logging()
        logger.info("HTTP 服务启动")
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=random.randint(80, 25565))
        parser.add_argument("--max-concurrent", type=int, default=2)
        parser.add_argument("--no-start-msg", action="store_true", help=argparse.SUPPRESS)
        options, _unknown_args = parser.parse_known_args()
        if options.max_concurrent < 1:
                parser.error("--max-concurrent must be at least 1")
        try:
                server = LoadSheddingHTTPServer((options.host, options.port), Handler, options.max_concurrent)
        except OSError as exc:
                if exc.errno not in (98, 10013, 10048):
                        raise
                logger.warning("端口 %s 不可用，将自动选择可用端口", options.port)
                server = LoadSheddingHTTPServer((options.host, 0), Handler, options.max_concurrent)
        server_instance = server
        logger.info("HTTP 服务监听地址：http://%s:%s", options.host, server.server_port)
        port = server.server_port
        ready_event.set()

        try:
                server.serve_forever()
        except KeyboardInterrupt:
                pass
        finally:
                server.server_close()
                server_instance = None


def stop():
        """停止 HTTP 服务线程。"""
        if server_instance is not None:
                server_instance.shutdown()

import threading
main_thread = threading.Thread(target=main)

if __name__ == "__main__":

        main_thread.start()
        main_thread.join()