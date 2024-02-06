import datetime as dt
import logging
import os
import threading
import time
import traceback
from urllib.parse import urlparse

import requests
from flask import request
from gevent.pywsgi import WSGIServer

logger = logging.getLogger(__name__)

tasks = {}


def extract_ip_from_url(url):
    parsed_url = urlparse(url)
    return parsed_url.hostname


def add_task(name, target, **options):
    tasks[name] = {
        "name": name,
        "target": target,
        "options": options
    }


def xxljob(name, **options):
    def decorator(f):
        logger.info(f"Added xxl-job handler {name} {options}")
        add_task(name, f, **options)
        return f
    return decorator


class Task():
    job_id = None
    name = None
    param = None
    fn = None
    start_time = None
    end_time = None
    exector = None
    status = None

    def __init__(self, excutor, param, fn):
        self.exector = excutor
        self.start_time = time.time()
        self.param = param
        self.fn = fn
        self.job_id = param['jobId']
        self.name = param['executorHandler']
        self.run()

    def run(self):
        self.worker = threading.Thread(target=self.doRun)
        self.worker.start()

    def doRun(self):
        try:
            task_response = self.fn(self.param)
            self.end_time = time.time()
            self.exector.callback(self.param, self.end_time, {
                                  "code": 200, "msg": task_response})
            duration = self.end_time - self.start_time
            logger.info(
                f"Task {self.name} run successfuly, duration: {str(dt.timedelta(seconds=round(duration, 6)))}")
        except:
            logger.error(
                f"Task {self.name} run failed: {traceback.format_exc()}")
            self.exector.callback(
                self.param, time.time(), {"code": 500, "msg": traceback.format_exc()})
        finally:
            self.done()

    def done(self):
        self.exector.done(self.job_id)

    def kill(self):
        pass


class PyXxlJobExecutor():
    server_address = None
    xxljob_admin_address = None
    access_token = None
    executor_host = None
    executor_port = None
    executor_name = None
    task_scan = None
    server_address_loader = None
    running_map = {}

    def __init__(self, config={}):
        self.server_address_loader = self.safeGet(
            config, "server_address_loader")
        self.server_address = self.safeGet(config, "server_address")
        self.access_token = self.safeGet(config, "access_token")
        self.executor_host = self.safeGet(config, "executor_host")
        self.executor_port = self.safeGet(config, "executor_port")
        self.executor_name = self.safeGet(config, "executor_name")
        self.task_scan = self.safeGet(config, "task_scan")
        logger.info(f"Task_scan is {self.task_scan}")
        if self.task_scan:
            for module in self.task_scan:
                try:
                    self.jobScan(module)
                except:
                    logger.warning("Can not import: {} {}".format(
                        module, traceback.format_exc()))

    def jobScan(self, module):
        folder = module.replace(".", "/")
        logger.info(f"Scaning {folder}")
        if os.path.exists(folder) and os.path.isdir(folder):
            for _ in os.listdir(folder):
                if os.path.splitext(_)[1] == '.py':
                    file = _.split('.')[0]
                    __import__(module+'.'+file)
                    logger.info(f"Scaned module {module+'.'+file}")
        else:
            logger.info(f"Module {module} not exists or is not a dir.")

    def safeGet(self, dic, key):
        if key in dic:
            return dic[key]
        return None

    def startDaemon(self):
        self.executorDaemon = threading.Thread(target=self.doStart)
        self.executorDaemon.setDaemon(True)
        self.executorDaemon.start()

    def startSync(self):
        self.startDaemon()
        self.executorDaemon.join()

    def done(self, job_id):
        self.running_map.pop(job_id)

    def doStart(self):
        from flask import Flask
        app = Flask(__name__)
        srv = WSGIServer(('0.0.0.0', self.executor_port),
                         app,
                         log=logger)

        # {'jobId': 2,
        #  'executorHandler': 'Job_Test',
        #  'executorParams': '{\n"key":123\n}',
        #  'executorBlockStrategy': 'SERIAL_EXECUTION',
        #  'executorTimeout': 0,
        #  'logId': 9,
        #  'logDateTime': 1707040340482,
        #  'glueType': 'BEAN',
        #  'glueSource': '',
        #  'glueUpdatetime': 1707037096000,
        #  'broadcastIndex': 0,
        #  'broadcastTotal': 1
        # }
        @app.route("/run", methods=["POST"])
        def run(**options):
            data = request.get_json()
            logger.info(f"{data} , {options}")
            job_id = data['jobId']
            job_name = data['executorHandler']
            if job_name not in tasks:
                return {'code': 500, 'msg': "Not found excutor handler."}
            block_strategy = data['executorBlockStrategy']
            if job_id in self.running_map:
                logger.warning(f"task {job_id} is running...")
                return {'code': 500, 'msg': "Task is running, ignored."}
            else:
                self.running_map[job_id] = Task(
                    self, data, tasks[job_name]["target"])
            return {'code': 200, 'msg': None, 'content': None}

        @app.route("/beat", methods=["POST"])
        def beat(**options):
            data = request.get_json()
            logger.info(f"Calling beat... {data} , {options}")
            return {'code': 200, 'msg': None, 'content': None}

        @app.route("/idleBeat", methods=["POST"])
        def idleBeat(**options):
            data = request.get_json()
            logger.info(f"Calling idleBeat... {data} , {options}")
            return {'code': 200, 'msg': None, 'content': None}

        @app.route("/kill", methods=["POST"])
        def kill(**options):
            data = request.get_json()
            logger.info(f"Calling kill... {data} , {options}")
            return {'code': 200, 'msg': None, 'content': None}

        @app.route("/log", methods=["POST"])
        def log(**options):
            data = request.get_json()
            logger.info(f"Calling log... {data} , {options}")
            return {'code': 200, 'msg': None, 'content': None}
        srv.start()
        self.registry()
        srv.serve_forever()
        self.remove()

    def registry(self):
        threading.Thread(target=self.doRegistry).start()

    def refreshXxlJobAdminAddress(self):
        if self.server_address_loader:
            self.xxljob_admin_address = self.server_address_loader()
        elif self.server_address:
            self.xxljob_admin_address = self.server_address
        else:
            raise Exception("Not found xxljob admin address")

    def refreshExcutorHost(self):
        if "192.168" in self.xxljob_admin_address:
            self.executor_host = extract_ip_from_url(self.xxljob_admin_address)
            pass
        if not self.executor_host:
            import socket

            # 获取本机的主机名
            hostname = socket.gethostname()
            # 获取本机的IP地址
            ip_address = socket.gethostbyname(hostname)
            logger.info("Xxl excutor host name:" + hostname)
            logger.info("Xxl excutor host ip:" + ip_address)
            self.executor_host = ip_address

    def callback(self, param, end_time, data):
        self.postXxlAdmin("/api/callback", [{
            "logId": param["logId"],
            "jobId": param["jobId"],
            "logDateTim": int(end_time*1000),
            "excuteResult": data,
            "handleCode": data['code'],
            "handleMsg": data['msg']
        }])

    def postXxlAdmin(self, endpoint, data, log=True):
        try:
            if log:
                logger.info(
                    f"post xxl admin {self.xxljob_admin_address}{endpoint} with {data}")
            response = requests.post(
                f"{self.xxljob_admin_address}{endpoint}", json=data, headers={"XXL-JOB-ACCESS-TOKEN": self.access_token, "Content-Type": "application/json;charset=UTF-8"})
            return response.json()
        except:
            logger.error(
                f"Post xxl job admin failed {traceback.format_exc()}")
            return {"code": 500, "msg": traceback.format_exc()}

    def doRegistry(self):
        inited = False
        while True:
            try:
                self.refreshXxlJobAdminAddress()
                self.refreshExcutorHost()
                data = {
                    "registryGroup": "EXECUTOR",
                    "registryKey": self.executor_name,
                    "registryValue": f"http://{self.executor_host}:{self.executor_port}",
                }
                response = self.postXxlAdmin(
                    "/api/registry", data, log=not inited)
                if not inited:
                    logger.info(
                        f"Registied xxl excutor {self.executor_name} {response}")
                    inited = True
            except:
                logger.error(
                    f"Registry xxl excutor failed {traceback.format_exc()}")
            time.sleep(20)

    def remove(self):
        import requests
        data = {
            "registryGroup": "EXECUTOR",
            "registryKey": self.executor_name,
            "registryValue": f"http://{self.executor_host}:{self.executor_port}",
        }
        response = requests.post(
            f"{self.server_address}/api/registryRemove", json=data, headers={"XXL-JOB-ACCESS-TOKEN": self.access_token, "Content-Type": "application/json;charset=UTF-8"})
        logger.info(response.json())
        logger.info(u'Removed')
