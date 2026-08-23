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


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

thread_num = 4
thread_work_list = [[] for i in range(thread_num)]
data_update_target_version = -1
data_update_url = ""
data_update_flag = False
data_update_lock = threading.Lock()
thread_sleep_flag = False


def node_url(node: str, path: str) -> str:
    """根据发现的节点地址构造 HTTP 接口地址。"""
    base_url = node if node.startswith(("http://", "https://")) else f"http://{node}"
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip('/'))

def thread_work(num):
    global temp_for_thread_init
    global data_update_target_version
    global data_update_url
    global data_update_flag
    logger.info("工作线程 %s 已启动", num)
    temp_for_thread_init = False
    while True:
        while thread_sleep_flag:
            logger.debug("工作线程 %s 正在等待任务", num)
            time.sleep(0.5)
        if thread_work_list[num]:
            task = thread_work_list[num].pop(0)
            logger.info("工作线程 %s 正在查询节点 %s", num, task)
            try:
                response = requests.get(node_url(task, "/query"), headers=auth_headers(), timeout=5)
                if response.status_code == 500:
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
    httpholder.main_thread.start()
    if not httpholder.ready_event.wait(timeout=10):
        raise RuntimeError("HTTP server did not become ready in time")
    port = httpholder.port
    Discovery = friend_finder.FriendFinder(app_name="smart-cr", app_port=port)
    Discovery.start()
    thread_sleep_flag = True
    for i in range(thread_num):
        t = threading.Thread(target=thread_work, args=(i,), daemon=True)
        t.start()
        temp_for_thread_init = True
        while temp_for_thread_init:
            time.sleep(0.1)
    while True:
        time.sleep(1)
        node_list = [a_node for a_node in Discovery.get_usable_list()]
        logger.info("发现节点：%s", node_list)
        thread_sleep_flag = False  # 唤醒工作线程处理任务
        logger.info("开始向工作线程分配任务")
        for i, node in enumerate(node_list):
            thread_work_list[i % thread_num].append(node)
        node_list.clear()
        logger.info("所有任务已分配，等待线程完成")
        while [len(l) for l in thread_work_list] != [0 for _ in range(thread_num)]:
            time.sleep(0.5)
        logger.info("所有线程已完成任务")
        thread_sleep_flag = True  # 让工作线程进入等待状态
        if data_update_flag:
            with data_update_lock:
                logger.info("发现新数据版本 %s，来源：%s", data_update_target_version, data_update_url)
                logger.info("开始下载数据")
                download_file(node_url(data_update_url, "/download"), "data/data.zip")
                data_update_flag = False
                data_update_target_version = -1
                data_update_url = ""


if __name__ == "__main__":
    main()
