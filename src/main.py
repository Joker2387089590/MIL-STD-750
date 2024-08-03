from PySide6 import QtWidgets
from .resist import *
from .main_ui import Ui_MainWindow

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup_ui(Ui_MainWindow())

    def update_serial_info(self):
        self.ports = QSerialPortInfo.availablePorts()

    def setup_ui(self, ui: Ui_MainWindow):
        self.ui = ui
        ui.setupUi(self)

    def connect_dmm(self):
        ...

    def connect_resist(self):
        self.ui.port.currentIndex()




def main():
    app = QtWidgets.QApplication()
    w = MainWindow()
    w.show()
    return app.exec()

if __name__ == '__main__':
    exit(main())
