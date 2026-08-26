import json
import time
import os
from zipfile import ZipFile
import httpholder
import friend_finder
import threading
import requests
import version_query
from zipfile import BadZipFile
import logging
import time
from urllib.parse import urljoin
from friend_finder import generate_token
from logging_setup import configure_logging


logger = logging.getLogger("数据同步服务")
configure_logging()

thread_num = 4
thread_work_list = [[] for i in range(thread_num)]
worker_threads = []
stop_event = threading.Event()
data_update_target_version = -1
data_update_url = ""
data_update_flag = False
data_update_lock = threading.Lock()
thread_sleep_flag = False


def node_url(node: str, path: str) -> str:
    """根据发现的节点地址构造 HTTP 接口地址。"""
    base_url = node if node.startswith(("http://", "https://")) else f"http://{node}"
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip('/'))

def thread_work(num, discovery):
    global temp_for_thread_init
    global data_update_target_version
    global data_update_url
    global data_update_flag
    logger.info("工作线程 %s 已启动", num)
    temp_for_thread_init = False
    while not stop_event.is_set():
        while thread_sleep_flag and not stop_event.is_set():
            logger.debug("工作线程 %s 正在等待任务", num)
            stop_event.wait(0.5)
        if stop_event.is_set():
            break
        if thread_work_list[num]:
            task = thread_work_list[num].pop(0)
            logger.info("工作线程 %s 正在查询节点 %s", num, task)
            try:
                response = requests.get(node_url(task, "/query"), headers=auth_headers(), timeout=5)
                if response.status_code == 500:
                    logger.warning(f"节点{task} 负载过高，跳过。")
                    continue
                elif response.status_code == 200:
                    logger.info("工作线程 %s 从 %s 收到数据版本 %s", num, task, response.text)
                    logger.info("当前本地版本：%s，节点版本：%s", version_query.get_version(), response.text)
                    if float(response.text) > version_query.get_version() and float(response.text) > data_update_target_version:
                        with data_update_lock:
                            logger.info("工作线程 %s 在 %s 发现新数据版本 %s", num, task, response.text)
                            data_update_target_version = float(response.text)
                            data_update_url = task
                            data_update_flag = True
                else:
                    logger.warning("工作线程 %s 收到节点错误：%s - %s", num, response.status_code, response.text)

            except requests.exceptions.ConnectionError as error:
                discovery.remove_peer(task)
                logger.warning("工作线程 %s 查询节点 %s 失败，已从节点缓存移除：%s", num, task, error)
            except (requests.RequestException, ValueError) as error:
                logger.warning("工作线程 %s 查询节点 %s 失败：%s", num, task, error)
            except Exception:
                logger.exception("工作线程 %s 查询节点 %s 时发生未预期错误", num, task)


def auth_headers():
    timestamp = time.time()
    return {
        "X-Auth-Timestamp": str(timestamp),
        "X-Auth-Token": generate_token(timestamp),
    }


def download_file(url: str, save_path: str) -> None:
    """下载并校验数据压缩包，然后以原子方式替换本地文件。"""
    temporary_path = f"{save_path}.tmp"
    try:
        directory = os.path.dirname(save_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        response = requests.get(url, headers=auth_headers(), stream=True, timeout=30)
        response.raise_for_status()

        with open(temporary_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)

        with ZipFile(temporary_path) as archive:
            if archive.testzip() is not None or "data.json" not in archive.namelist():
                raise BadZipFile("downloaded archive is invalid or missing data.json")

        os.replace(temporary_path, save_path)
        logger.info("文件下载完成：%s", save_path)
    except requests.RequestException as error:
        logger.warning("下载请求失败：%s", error)
    except (OSError, BadZipFile) as error:
        logger.warning("下载或压缩包校验失败：%s", error)
    except Exception:
        logger.exception("下载 %s 时发生未预期错误", url)
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            logger.exception("删除临时下载文件 %s 失败", temporary_path)


def main():
    global temp_for_thread_init
    global thread_sleep_flag
    global data_update_flag
    global data_update_target_version
    global data_update_url
    logger.info("智能课程表同步程序启动")
    discovery = None
    try:
        httpholder.main_thread.start()
        if not httpholder.ready_event.wait(timeout=10):
            raise RuntimeError("HTTP 服务未能在规定时间内启动")
        port = httpholder.port
        discovery = friend_finder.FriendFinder(app_name="smart-cr", app_port=port)
        discovery.start()
        thread_sleep_flag = True
        for i in range(thread_num):
            t = threading.Thread(target=thread_work, args=(i, discovery), daemon=True, name=f"工作线程-{i}")
            worker_threads.append(t)
            t.start()
            temp_for_thread_init = True
            while temp_for_thread_init and not stop_event.is_set():
                stop_event.wait(0.1)
        while not stop_event.is_set():
            stop_event.wait(discovery.interval)
            if stop_event.is_set():
                break
            node_list = [a_node for a_node in discovery.get_usable_list()]
            logger.info("发现节点：%s", node_list)
            thread_sleep_flag = False  # 唤醒工作线程处理任务
            logger.info("开始向工作线程分配任务")
            for i, node in enumerate(node_list):
                thread_work_list[i % thread_num].append(node)
            node_list.clear()
            logger.info("所有任务已分配，等待线程完成")
            while [len(l) for l in thread_work_list] != [0 for _ in range(thread_num)]:
                if stop_event.wait(0.5):
                    break
            logger.info("所有线程已完成任务")
            thread_sleep_flag = True  # 让工作线程进入等待状态
            if data_update_flag and not stop_event.is_set():
                with data_update_lock:
                    logger.info("发现新数据版本 %s，来源：%s", data_update_target_version, data_update_url)
                    logger.info("开始下载数据")
                    download_file(node_url(data_update_url, "/download"), "data/data.zip")
                    logger.info("数据下载完成，当前版本：%s", version_query.get_version())
                    data_update_flag = False
                    data_update_target_version = -1
                    data_update_url = ""
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，开始停止所有线程")
    finally:
        stop_event.set()
        thread_sleep_flag = False
        if discovery is not None:
            discovery.stop()
        httpholder.stop()
        for worker_thread in worker_threads:
            worker_thread.join(timeout=6)
        if httpholder.main_thread.is_alive():
            httpholder.main_thread.join(timeout=6)
        logger.info("我将用最简洁最不绕弯子最直白最一听就懂的大白话告诉你，所有线程已停止，程序退出")
        exit(0)


if __name__ == "__main__":
    main()
# 我将用最简洁最不绕弯子最直白最一听就懂的大白话告诉你