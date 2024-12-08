import sys, debugpy, logging, json
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from PySide6 import QtWidgets
from PySide6.QtCore import QThread, Slot, QTimer
from .refer import ReferPanel
from .device import DevicePanel
from .worker import Worker, log as worker_log
from .scope import Scope
from . import global_logger

_config = Path(__file__).with_name('config.json')

class DebugThread(QThread):
    def run(self):
        debugpy.debug_this_thread()
        return super().run()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('晶体管安全工作区测试平台')
    
        self.io_thread = DebugThread(self)
        self.context = Worker()
        self.context.moveToThread(self.io_thread)

        self.tab = QtWidgets.QTabWidget(self)
        self.refer = ReferPanel(self.tab)
        self.devices = DevicePanel(self.tab)
        self.logs = QtWidgets.QPlainTextEdit(self.tab)
        self.tab.addTab(self.refer, '参考测试')
        self.tab.addTab(self.devices, '设备管理')
        self.tab.addTab(Scope(self.tab), '示波器工具')
        self.tab.addTab(self.logs, '测试日志')
        self.setCentralWidget(self.tab)

        self.refer.startRequested.connect(self.start)
        self.refer.abortRequested.connect(self.abort)
        self.context.stateChanged.connect(self.update_running_state)
        self.context.logged.connect(self.logs.appendHtml)

    def __enter__(self):
        self.load()
        self.io_thread.start()
        self.show()
        return self

    def __exit__(self, *exception):
        self.io_thread.quit()
        self.io_thread.wait()
        self.save()

    def start(self):
        self.refer.restart()
        arg = self.refer.get_arguments() # .................
        dev = self.devices.get_devices()
        QTimer.singleShot(0, self.context, lambda: self.context.start(arg, dev))

    def abort(self):
        self.context.abort()

    @Slot()
    def update_running_state(self, running: bool):
        self.refer.update_running_state(running)
        self.devices.setDisabled(running)

    def save(self):
        data = dict(
            refer=self.refer.save()
        )
        with open(_config, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load(self):
        with open(_config, 'r', encoding='utf-8') as f:
            data: dict = json.load(f)
        self.refer.load(data.get('refer', None))

def config_logs():
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

    for h in [handler_out, handler_err, file]: 
        global_logger.addHandler(h)

def main():
    config_logs()

    QtWidgets.QApplication.setDesktopSettingsAware(False)
    app = QtWidgets.QApplication()

    style = Path(__file__).with_name('style.qss')
    with open(style, 'r', encoding='UTF-8') as file:
        app.setStyleSheet(file.read())
    
    with MainWindow():
        return app.exec()

if __name__ == '__main__':
    exit(main())
