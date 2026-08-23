import json
import os
from zipfile import ZipFile
from zipfile import BadZipFile

archive_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "data.zip")
def get_version():
    try:
        with ZipFile(archive_path) as archive:
            with archive.open("data.json") as file:
                data = json.load(file)
        return float(data.get("version", "1.1"))
    except (FileNotFoundError, BadZipFile, KeyError, json.JSONDecodeError, TypeError, ValueError):
        return -1.114514

def main():
    print("Hello from smart-cr!This is the model of 'version_query'")
    print(f"Version from data.json: {get_version()}")

if __name__ == "__main__":
    main()
