"""配置应用控制台日志和每日滚动日志"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from config import settings

LOG_DIR = "logs"
#日志目录不存在时自动创建
os.makedirs(LOG_DIR, exist_ok=True)

#使用命名logger，避免直接修改python全局root logger
logger = logging.getLogger("app")
#Debug模式输出DEBUG及以上日志
#非Debug环境只输出INFO及以上日志
logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
#禁止向root logger继续传播
#防止同一条日志被多个Handler重复输出
logger.propagate = False

#m模块重新导入或热重载时可能再次执行此文件
#只有还没有Handler时才添加，避免重复记录
#日志格式为：时间|级别|信息
if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    #StreamHandler将日志输出到终端，便于本地调试和查看Docker日志
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_DIR, "app.log"),
        #每天午夜切割一次日志文件
        when="midnight",
        interval=1,
        #最多保留7份历史日志文件
        backupCount=7,
        #使用UTF8保存日志，避免中文乱码
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
