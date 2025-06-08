import sys, debugpy, logging, json
from typing import Protocol
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import QThread, Signal, Qt, QTimer

from .types import *
from .refer import ReferPanel
from .exec import ExecPanel
from .device import DevicePanel
from .worker import Worker
from .scope import Scope
from .dmm import plc_to_rate
from . import global_logger

from .refer.task import ReferRunner
from .worker.common import Context

_log = logging.getLogger(__name__)
_config = Path(__file__).with_name('config.json')

def debugger_is_active() -> bool:
    """Return if the debugger is currently active"""
    return hasattr(sys, 'gettrace') and sys.gettrace() is not None

class _Common(Protocol):
    def update_running_state(self, running: bool): ...
    def start_target(self): ...
    def set_disabled(self, disabled: bool): ...
    
class UiHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__(logging.INFO)
        self.signal = signal
        self.setFormatter(logging.Formatter(
            fmt='[{asctime}.{msecs:03.0f}][{levelname}] {message}',
            datefmt='%H:%M:%S',
            style='{'
        ))

    def emit(self, record):
        msg = self.format(record)

        if record.levelno >= logging.FATAL:
            fore, back = 'rgb(255, 255, 255)', 'rgb(190, 0, 0)'
        elif record.levelno >= logging.ERROR:
            fore, back = 'rgb(240, 0, 0)', 'rgb(255, 255, 255)'
        elif record.levelno >= logging.WARNING:
            fore, back = 'rgb(225, 125, 50)', 'rgb(255, 255, 255)'
        elif record.levelno >= logging.INFO:
            fore, back = 'rgb(0, 125, 60)', 'rgb(255, 255, 255)'
        else:
            fore, back = 'rgb(54, 96, 146)', 'rgb(255, 255, 255)'
        
        html = f'<pre style="color: {fore}; background-color: {back}">{msg}</pre>'
        self.signal.emit(html)

class DebugThread(QThread):
    def run(self):
        if debugger_is_active():
            debugpy.debug_this_thread()
        return super().run()

class MainWindow(QtWidgets.QMainWindow):
    logged = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('晶体管安全工作区测试平台')
    
        self.io_thread = DebugThread(self)

        self.worker = Worker()
        self.worker.moveToThread(self.io_thread)

        self.context = Context()
        self.context.moveToThread(self.io_thread)

        self.tab = QtWidgets.QTabWidget(self)
        self.refer = ReferPanel(self.tab)
        self.exec = ExecPanel(self.tab)
        self.devices = DevicePanel(self.tab)
        self.logs = QtWidgets.QPlainTextEdit(self.tab)
        self.tab.addTab(self.refer, '参考测试')
        self.tab.addTab(self.exec, '持续测试')
        self.tab.addTab(self.devices, '设备管理')
        self.tab.addTab(Scope(self.tab), '示波器工具')
        self.tab.addTab(self.logs, '运行日志')
        self.setCentralWidget(self.tab)

        self.refer.startRequested.connect(self.start_refer)
        self.refer.abortRequested.connect(self.abort)
        self.refer.closed.connect(self.save)

        self.exec.startRequested.connect(self.start_exec)
        self.exec.abortRequested.connect(self.abort)

        self.worker.stateChanged.connect(self.update_running_state)
        self.worker.targetStarted.connect(self.start_target)
        self.worker.message.connect(self.message)

        self.context.stateChanged.connect(self.update_running_state)
        self.context.targetStarted.connect(self.start_target)
        self.context.message.connect(self.message)

        self.worker.referTested.connect(self.add_refer)
        self.worker.referComplete.connect(self.exec.receive_refer_all_results)

        self.worker.execTested.connect(self.receive_exec)
        self.worker.execComplete.connect(self.exec.receive_exec_all_results)
        # self.context.plots.connect(self.plot)

        self.common: _Common | None = None

        self.config_logs()
        # self._init_plot()

    def _init_plot(self):
        self.fig_V, self.ax_V = plt.subplots()
        self.fig_I, self.ax_I = plt.subplots()

    def plot(self, results, name, type):
        def sample_duration(point: int, plc: str):
            rate = plc_to_rate[plc]
            return point / rate
        
        if type == 'V':
            fig, ax = self.fig_V, self.ax_V
        else:
            fig, ax = self.fig_I, self.ax_I

        _log.info(f'[plot] {name} {len(results)}')
        d = sample_duration(len(results), "0.1")
        times = np.linspace(0, d, len(results))
        ax.plot(times, results, '.-')

        ax.set_title(name)
        fig.show()

    def config_logs(self):
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        global_logger.setLevel(logging.DEBUG)
        # global_logger.setLevel(logging.INFO)

        console_fmt = logging.Formatter(
            fmt='[{asctime}.{msecs:03.0f}][{levelname}][{module}:{lineno}] {message}',
            datefmt='%H:%M:%S',
            style='{'
        )

        handler_out = logging.StreamHandler(sys.stdout)
        handler_out.setLevel(logging.DEBUG)
        handler_out.addFilter(lambda r: logging.DEBUG <= r.levelno < logging.ERROR)
        handler_out.setFormatter(console_fmt)

        handler_err = logging.StreamHandler(sys.stderr)
        handler_err.setFormatter(console_fmt)
        handler_err.setLevel(logging.ERROR)

        dnow = datetime.now()
        _log_dir = Path(__file__).parent.with_name('logs')
        folder = _log_dir / f'{dnow:%Y-%m}'
        folder.mkdir(parents=True, exist_ok=True)
        file = RotatingFileHandler(filename=folder / f'{dnow:%Y%m%d}.log', encoding='utf-8')
        file.setFormatter(logging.Formatter(
            fmt='[{asctime}.{msecs:03.0f}][{levelname}][{name}({filename}):{lineno}] {message}',
            datefmt='%Y-%m-%d %H:%M:%S',
            style='{'
        ))
        file.setLevel(logging.INFO)

        ui_handler = UiHandler(self.logged)
        self.logged.connect(self.logs.appendHtml, Qt.ConnectionType.QueuedConnection)

        for h in [handler_out, handler_err, file, ui_handler]: 
            global_logger.addHandler(h)

    def __enter__(self):
        self.load()
        self.io_thread.start()
        self.show()
        return self

    def __exit__(self, *exception):
        self.io_thread.quit()
        self.io_thread.wait()
        self.save()

    def start_refer(self):
        self.common = self.refer
        self.refer.restart()
        arg = self.refer.get_arguments()
        dev = self.devices.get_devices()

        def build_runner(context: Context):
            runner = ReferRunner(arg, context)
            runner.referTested.connect(self.add_refer)
            runner.referComplete.connect(self.exec.receive_refer_results)
            return runner

        def run():
            # self.worker.start(arg, dev)
            self.context.start(arg.type, dev, build_runner)
            
        # QTimer.singleShot(0, self.worker, run)
        QTimer.singleShot(0, self.context, run)

    def start_exec(self):
        self.common = self.exec
        self.exec.restart()
        arg = self.exec.get_arguments()
        dev = self.devices.get_devices()

        def run(): self.worker.start(arg, dev)
        QTimer.singleShot(0, self.worker, run)

    def start_target(self):
        if self.common:
            self.common.start_target()

    def add_refer(self, result: ReferResult):
        self.refer.add_refer(result)
        self.refer.add_test_point(abs(result.Vce), result.Ic)
        if 0:
            fig, (axv, axi) = plt.subplots(2, 1)
            axv.plot(result.all_vce, label='Vce')
            axv.plot(result.all_dmm2, label='Vbe(NPN)/Vcb(PNP)')
            axv.plot(result.all_dmm3, label='Vcb(NPN)/Veb(PNP)')
            axi.plot(result.all_ic, label='Ic')
            axi.plot(result.all_ie, label='Ie')
            fig.show()

    def receive_exec(self, exec: ExecResult):
        self.exec.receive_exec_result(exec)

    def abort(self):
        self.worker.abort()
        self.context.abort()

    def update_running_state(self, running: bool):
        for c in [self.refer, self.exec]:
            c: _Common
            if c is self.common:
                assert self.common is not None
                self.common.update_running_state(running)
            else:
                c.set_disabled(running)
        self.devices.setDisabled(running)

    def message(self, msg):
        QtWidgets.QMessageBox.information(self, '信息', msg)

    def save(self):
        data = dict(
            refer=self.refer.save(),
            devices=self.devices.save(),
            exec=self.exec.save(),
        )
        with open(_config, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        _log.info('已保存配置')

    def load(self):
        if _config.exists():
            with open(_config, 'r', encoding='utf-8') as f:
                data: dict = json.load(f)
            self.refer.load(data.get('refer', {}))
            self.devices.load(data.get('devices', {}))
            self.exec.load(data.get('exec', {}))
            _log.info('已加载上次运行的配置')

def main():
    QtWidgets.QApplication.setDesktopSettingsAware(False)
    app = QtWidgets.QApplication()

    style = Path(__file__).with_name('style.qss')
    with open(style, 'r', encoding='UTF-8') as file:
        app.setStyleSheet(file.read())
    
    with MainWindow():
        return app.exec()
