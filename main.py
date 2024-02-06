import logging

from excutor import PyXxlJobExecutor

logger = logging.getLogger('default')
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(pathname)s:%(lineno)s %(funcName)s() %(levelname)s - [%(message)s]")

PyXxlJobExecutor(config={
    "server_address": "http://192.168.110.25:8040/xxl-job-admin",
    "access_token": "DEFAULT_TOKEN",
    "executor_host": None,
    "executor_port": 9998,
    "executor_name": "archery",
    "task_scan": ["xxljob.task"]
}).startSync()
