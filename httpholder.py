"""Small HTTP server exposing the download and query endpoints."""

import importlib.util
import json
import mimetypes
import version_query
import random
import os
import threading
from friend_finder import verify_token
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


ROOT = os.path.dirname(os.path.abspath(__file__))


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
			self._send(500, "Server overloaded")
			return
		try:
			self._do_get()
		finally:
			self.server.request_slots.release()

	def _do_get(self):
		"""响应拉取课程表数据行为"""
		if not self._authorized():
			self._send(401, "Unauthorized")
			return
		request = urlparse(self.path)
		if request.path == "/download":
			path = os.path.join(ROOT, "data", "data.zip")
			if not os.path.isfile(path):
				self._send(404, "data/data.zip not found")
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
			main_path = os.path.join(ROOT, "main.py")
			if not os.path.isfile(main_path):
				self._send(404, "main.py not found")
				return
			try:
				result = version_query.get_version()
				self._send(200, str(result))
			except (AttributeError, TypeError, ValueError) as exc:
				self._send(400, str(exc))
			except Exception as exc:
				self._send(500, str(exc))
			return

		self._send(404, "Not found")

	def log_message(self, format, *args):
		print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))


class LoadSheddingHTTPServer(ThreadingHTTPServer):
	def __init__(self, server_address, handler_class, max_concurrent):
		super().__init__(server_address, handler_class)
		self.request_slots = threading.BoundedSemaphore(max_concurrent)
port = 0
ready_event = threading.Event()
def main():
	global port
	print("Hello from http-model of smart-cr!")
	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument("--host", default="0.0.0.0")
	parser.add_argument("--port", type=int, default=random.randint(80, 25565))
	parser.add_argument("--max-concurrent", type=int, default=2)
	options = parser.parse_args()
	if options.max_concurrent < 1:
		parser.error("--max-concurrent must be at least 1")
	try:
		server = LoadSheddingHTTPServer((options.host, options.port), Handler, options.max_concurrent)
	except OSError as exc:
		if exc.errno not in (98, 10013, 10048):
			raise
		print(f"Port {options.port} is unavailable; selecting an available port.")
		server = LoadSheddingHTTPServer((options.host, 0), Handler, options.max_concurrent)
	print(f"Serving on http://{options.host}:{server.server_port}")
	port = server.server_port
	ready_event.set()

	try:
		server.serve_forever()
	except KeyboardInterrupt:
		pass
	finally:
		server.server_close()

import threading
main_thread = threading.Thread(target=main)

if __name__ == "__main__":

	main_thread.start()
	main_thread.join()