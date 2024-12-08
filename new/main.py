import sys, debugpy, logging, json
from typing import Protocol
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from PySide6 import QtWidgets
from PySide6.QtCore import QThread, Signal, Slot, QTimer
from .types import *
from .refer import ReferPanel
from .exec import ExecPanel
from .device import DevicePanel
from .worker import Worker
from .scope import Scope
from . import global_logger

_log = logging.getLogger(__name__)
_config = Path(__file__).with_name('config.json')

class Common(Protocol):
    def update_running_state(self, running: bool): ...
    def restart(self): ...
    def start_target(self): ...
    def add_test_point(self, Vce: float, Ic: float): ...
    def add_refer(self, data: ReferResult): ...
    def take_refers(self) -> list[ReferResult]: ...
    
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
        debugpy.debug_this_thread()
        return super().run()

class MainWindow(QtWidgets.QMainWindow):
    logged = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('晶体管安全工作区测试平台')
    
        self.io_thread = DebugThread(self)
        self.context = Worker()
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
        self.context.stateChanged.connect(self.update_running_state)
        self.context.logged.connect(self.logs.appendHtml)

        self.common: Common | None = None

        self.config_logs()

    def config_logs(self):
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        global_logger.setLevel(logging.DEBUG)

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
        self.logged.connect(self.logs.appendHtml)

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

        def run(): self.context.start(arg, dev)
        QTimer.singleShot(0, self.context, run)

    def start_exec(self):
        self.common = self.exec
        self.exec.restart()
        arg = self.exec.get_arguments()
        dev = self.devices.get_devices()

        def run(): self.context.start(arg, dev)
        QTimer.singleShot(0, self.context, run)

    def abort(self):
        self.context.abort()

    def update_running_state(self, running: bool):
        self.refer.update_running_state(running)
        self.devices.setDisabled(running)

    def save(self):
        data = dict(
            refer=self.refer.save(),
            devices=self.devices.save(),
        )
        with open(_config, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        _log.info('已保存配置')

    def load(self):
        if _config.exists():
            with open(_config, 'r', encoding='utf-8') as f:
                data: dict = json.load(f)
            self.refer.load(data.get('refer', None))
            self.devices.load(data.get('devices', None))
            _log.info('已加载上次运行的配置')

def main():
    QtWidgets.QApplication.setDesktopSettingsAware(False)
    app = QtWidgets.QApplication()

    style = Path(__file__).with_name('style.qss')
    with open(style, 'r', encoding='UTF-8') as file:
        app.setStyleSheet(file.read())
    
    with MainWindow():
        return app.exec()

if __name__ == '__main__':
    exit(main())
