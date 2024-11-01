import json, debugpy
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Signal, Slot, QThread
from .context import Context
from .test import TestPanel
from .device import DevicePanel

class DebugThread(QThread):
    def run(self):
        debugpy.debug_this_thread()
        return super().run()
    
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('晶体管安全工作区测试平台')

        style = Path(__file__).with_name('style.qss')
        with open(style, 'r', encoding='UTF-8') as file:
            self.setStyleSheet(file.read())

        self.io_thread = DebugThread(self)
        self.tab = QtWidgets.QTabWidget(self)
        scroll = QtWidgets.QScrollArea(self.tab)
        self.devices = DevicePanel(scroll)
        self.tests = TestPanel(self.tab)
        self.context = Context()

        scroll.setWidget(self.devices)
        scroll.setWidgetResizable(True)

        self.tab.addTab(scroll, '设备管理')
        self.tab.addTab(self.tests, '测试管理')
        # TODO: add result view
        self.setCentralWidget(self.tab)

        self.context.moveToThread(self.io_thread)

        self.tests.startRequested.connect(self.start_test)
        self.tests.pauseRequested.connect(self.context.pause)
        self.tests.abortRequested.connect(self.context.abort)
        # self.devices.connectRequested.connect(self.context.connect_device)
        # self.devices.disconnectRequested.connect(self.context.disconnect_device)
        self.context.stateChanged.connect(self.update_running_state)
        # self.context.deviceChanged.connect(self.devices.update_state)
        self.context.npn_tested.connect(self.tests.add_npn_results)

        self.context.errorOccurred.connect(self.show_error)

        self.update_running_state('pass')

    def show_error(self, msg: str):
        QtWidgets.QMessageBox.critical(self, '发生错误', msg)

    def save(self):
        data = {
            'test': self.tests.save(),
            'device': self.devices.save(),
        }
        with open(Path(__file__).with_name('config.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False, allow_nan=True)
    
    def load(self):
        data = {}
        config = Path(__file__).with_name('config.json')
        if config.exists():
            with open(config, 'r', encoding='utf-8') as f:
                content = f.read()
                if content: data = data = json.loads(content)
        self.tests.load(data.get('test', dict()))
        self.devices.load(data.get('device', dict()))

    def __enter__(self):
        self.load()
        self.io_thread.start()
        self.show()
        return self
    
    def __exit__(self, *exception):
        self.io_thread.quit()
        self.io_thread.wait()
        self.save()

    @Slot()
    def start_test(self):
        self.tests.reset_chart()
        arg = self.tests.get_arguments()
        dev = self.devices.get_devices()
        QtCore.QTimer.singleShot(
            0, self.context,
            lambda: self.context.run(arg, dev))

    @Slot()
    def update_running_state(self, state: str):
        running = (state != 'pass') and (state != 'fail')
        self.tests.update_running_state(running)
        self.devices.setDisabled(running)

if __name__ == '__main__':
    app = QtWidgets.QApplication()
    with MainWindow() as w:
        ret = app.exec()
    exit(ret)
