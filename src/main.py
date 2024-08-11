import sys
import time
from PySide6 import QtWidgets
from PySide6.QtCore import Slot
from .resist import *
from .dmm import Meter
from .power import Power
from .main_ui import Ui_MainWindow

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setup_ui(Ui_MainWindow())
        self.resist: Resist = None
        self.dmm: Meter = None
        self.power_vc: Power = None
        self.power_vb: Power = None

    def setup_ui(self, ui: Ui_MainWindow):
        self.ui = ui
        ui.setupUi(self)

        self.update_serial_info()
        self.ui.Rset.addItems([f'P0{i}' for i in range(8)])

        ui.btnDebug.clicked.connect(self.debug)
        ui.btnConnect.clicked.connect(self.连接设备)
        ui.btnDisconnect.clicked.connect(self.断开设备)
        ui.btnRset.clicked.connect(self.设置电阻)
        ui.btnPin.clicked.connect(self.设置引脚)
        ui.btnVc.clicked.connect(self.设置Vc)
        ui.btnVc.clicked.connect(self.设置Vb)

    @Slot()
    def debug(self):
        pass

    def update_serial_info(self):
        self.ui.port.clear()
        self.ports = QSerialPortInfo.availablePorts()
        self.ui.port.addItems([port.portName() for port in self.ports])

    @Slot()
    def 连接设备(self):
        info = self.ports[self.ui.port.currentIndex()]
        self.ui.wControl.setEnabled(True)
        self.ui.btnConnect.setEnabled(False)
        self.ui.btnDisconnect.setEnabled(True)
        try:
            self.resist = Resist(info, self)
            self.dmm = Meter(self.ui.dmm.text())
            self.power_vc = Power(self.ui.powerVc.text())
            self.power_vb = Power(self.ui.powerVb.text())

            self.power_vc.set_current_protection(40 * 0.6) # 继电器

        except Exception as e:
            self.断开设备()
            print(e, file=sys.stderr)
    
    @Slot()
    def 断开设备(self):
        for dev in (self.resist, self.dmm, self.power_vc, self.power_vb):
            if dev is not None:
                dev.disconnects()
        self.resist, self.dmm, self.power_vc, self.power_vb = (None,) * 4

        self.ui.wControl.setDisabled(True)
        self.ui.btnConnect.setDisabled(False)
        self.ui.btnDisconnect.setDisabled(True)

    @Slot()
    def 设置电阻(self):
        res = 1 << self.ui.Rset.currentIndex()
        self.resist.write(f'{res:0>2X} {res:0>2X} FF FF')

    @Slot()
    def 设置引脚(self):
        self.resist.write(self.ui.pin.text())

    @Slot()
    def 设置Vb(self):
        self.power_vb.set_voltage(self.ui.Vb.value())

    @Slot()
    def 设置Vc(self):
        self.power_vc.set_voltage(self.ui.Vc.value())

    def test(self, vc: float, vb: float):
        self.power_vc.set_voltage(vc)
        self.power_vb.set_voltage(vb)

        self.power_vc.set_output_state(True)
        self.power_vb.set_output_state(True)

        try:
            time.sleep(0.100)
            self.dmm.set_function('DC')
            value = self.dmm.read()
        finally:
            self.power_vc.set_output_state(False)
            self.power_vb.set_output_state(False)
        
        return value



    def 第一阶段(self):
        Vc = 0.1
        Vb = 0.1
        while True:
            Vce = self.test(Vc, Vb)


        ...

def main():
    app = QtWidgets.QApplication()
    w = MainWindow()
    w.show()
    return app.exec()

if __name__ == '__main__':
    exit(main())
