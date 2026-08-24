import logging
import easygui
import os


logging.basicConfig(level=logging.INFO)


if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "for_classroom_device.py")):
    logging.info("提示，，当前存在有教室端，请确认是否需要使用教室端功能。")
    easygui.msgbox("当前存在有教室端，请确认是否需要使用教室端功能。", title="提示", ok_button="我知道了")
