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

thread_num = 4
thread_work_list = [[] for i in range(thread_num)]
data_update_target_version = -1
data_update_url = ""
data_update_flag = False
data_update_lock = threading.Lock()
thread_sleep_flag = False


def node_url(node: str, path: str) -> str:
    """Build an HTTP endpoint from a discovered node address."""
    base_url = node if node.startswith(("http://", "https://")) else f"http://{node}"
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip('/'))

def thread_work(num):
    global temp_for_thread_init
    global data_update_target_version
    global data_update_url
    global data_update_flag
    print(f"Thread {num} started.")
    temp_for_thread_init = False
    while True:
        while thread_sleep_flag:
            print(f"Thread {num} is waiting for task...")
            time.sleep(0.5)
        if thread_work_list[num]:
            task = thread_work_list[num].pop(0)
            print(f"Thread {num} is querying {task}...")
            try:
                response = requests.get(node_url(task, "/query"), headers=auth_headers(), timeout=5)
                if response.status_code == 500:
                    continue
                elif response.status_code == 200:
                    print(f"Thread {num} received version: {response.text} from {task}")
                    print(f"Current local version: {version_query.get_version()}, Current node version: {response.text}")
                    if float(response.text) > version_query.get_version() and float(response.text) > data_update_target_version:
                        with data_update_lock:
                            print(f"Thread {num} found new data version: {response.text} at {task}")
                            data_update_target_version = float(response.text)
                            data_update_url = task
                            data_update_flag = True
                else:
                    print(f"Thread {num} received error: {response.status_code} - {response.text}")

            except (requests.RequestException, ValueError) as error:
                logger.warning("Thread %s failed to query %s: %s", num, task, error)
            except Exception:
                logger.exception("Unexpected error in thread %s while querying %s", num, task)


def auth_headers():
    timestamp = time.time()
    return {
        "X-Auth-Timestamp": str(timestamp),
        "X-Auth-Token": generate_token(timestamp),
    }


def download_file(url: str, save_path: str) -> None:
    """下载文件"""
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
        print(f"Download completed: {save_path}")
    except requests.RequestException as error:
        logger.warning("Download request failed: %s", error)
    except (OSError, BadZipFile) as error:
        logger.warning("Download or archive validation failed: %s", error)
    except Exception:
        logger.exception("Unexpected error while downloading %s", url)
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            logger.exception("Failed to remove temporary download %s", temporary_path)


def main():
    global temp_for_thread_init
    global thread_sleep_flag
    global data_update_flag
    global data_update_target_version
    global data_update_url
    print("Hello from http-model 'main()' of smart-cr!")
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
        print(f"Discovered nodes: \n{node_list}")
        thread_sleep_flag = False # 使线程退出休息
        print("开始分配任务到线程...")
        for i, node in enumerate(node_list):
            thread_work_list[i % thread_num].append(node)
        node_list.clear()
        print("所有任务已分配，等待线程完成...")
        while [len(l) for l in thread_work_list] != [0 for _ in range(thread_num)]:
            time.sleep(0.5)
        print("所有线程已完成任务。")
        thread_sleep_flag = True # 使线程休息
        if data_update_flag:
            with data_update_lock:
                print(f"New data version {data_update_target_version} found at {data_update_url}.")
                print("Downloading...")
                download_file(node_url(data_update_url, "/download"), "data/data.zip")
                data_update_flag = False
                data_update_target_version = -1
                data_update_url = ""


if __name__ == "__main__":
    main()
