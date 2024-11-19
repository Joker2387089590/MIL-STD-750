import sys, json, debugpy, logging
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Slot, QThread
from .refer import ReferPanel
from .device import DevicePanel
from .worker import Worker
from . import global_logger

class DebugThread(QThread):
    def run(self):
        debugpy.debug_this_thread()
        return super().run()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('晶体管安全工作区测试平台')
    
        self.io_thread = DebugThread(self)
        self.tab = QtWidgets.QTabWidget(self)
        self.devices = DevicePanel(self.tab)
        self.refer = ReferPanel(self.tab)
        self.context = Worker()

        self.tab.addTab(self.refer, '参考测试')
        self.tab.addTab(self.devices, '设备管理')
        self.setCentralWidget(self.tab)

        self.context.moveToThread(self.io_thread)
    def __enter__(self):
        # self.load()
        self.io_thread.start()
        self.show()
        return self

    def __exit__(self, *exception):
        self.io_thread.quit()
        self.io_thread.wait()
        # self.save()

def main():
    # QtWidgets.QApplication.setDesktopSettingsAware(False)
    logging.basicConfig(filename='all.log')
    
    handler_out = logging.StreamHandler(sys.stdout)
    handler_out.setLevel(logging.DEBUG)
    # handler_out.setLevel(logging.INFO)
    handler_err = logging.StreamHandler(sys.stderr)
    handler_err.setLevel(logging.WARNING)
    for h in [handler_out, handler_err]:
        global_logger.addHandler(h)

    app = QtWidgets.QApplication()
    style = Path(__file__).with_name('style.qss')
    with open(style, 'r', encoding='UTF-8') as file:
        app.setStyleSheet(file.read())
    
    with MainWindow():
        return app.exec()

if __name__ == '__main__':
    exit(main())
