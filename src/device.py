from dataclasses import dataclass
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtSerialPort import QSerialPortInfo
from .device_ui import Ui_DevicePanel

@dataclass
class Devices:
    DMM1: str
    DMM2: str
    DMM3: str
    DMM4: str
    DMM5: str
    Power1: str
    Power2: str

class DevicePanel(QtWidgets.QWidget):
    connectRequested = Signal(str)
    disconnectRequested = Signal(str)

    def __init__(self, parent = None, f = Qt.WindowType.Widget):
        super().__init__(parent, f)
        self.ui = Ui_DevicePanel()
        self.devices: dict[str, QtWidgets.QLineEdit] = {}
        self.ui.setupUi(self)
        defines = [
            ('DMM1', '数字万用表 SDM4065A', 'Vce', '-Vce'),
            ('DMM2', '数字万用表 SDM4065A', 'Vbe', '-Vbc'),
            ('DMM3', '数字万用表 SDM4065A', 'Vcb', '-Veb'),
            ('DMM4', '数字万用表 SDM4065A', 'Ic', 'Ie'),
            ('DMM5', '数字万用表 SDM4065A', 'Ie', 'Ic'),
            ('Power1', '直流电源 IT-M3900D', 'Vc', 'Ve'),
            ('Power2', '直流电源 IT-M3900D', 'Ve', 'Vc'),
        ]
        for i, define in enumerate(defines):
            name, model, npn, pnp = define
            row = i + 1
            ip = QtWidgets.QLineEdit(self)
            self.ui.grid.addWidget(QtWidgets.QLabel(name, self), row, 0, Qt.AlignmentFlag.AlignCenter)
            self.ui.grid.addWidget(QtWidgets.QLabel(model, self), row, 1, Qt.AlignmentFlag.AlignCenter)
            self.ui.grid.addWidget(QtWidgets.QLabel(npn, self), row, 2, Qt.AlignmentFlag.AlignCenter)
            self.ui.grid.addWidget(QtWidgets.QLabel(pnp, self), row, 3, Qt.AlignmentFlag.AlignCenter)
            self.ui.grid.addWidget(ip, row, 4, Qt.AlignmentFlag.AlignCenter)
            self.devices[name] = ip

        self.ui.refreshPort.clicked.connect(self.update_serial_info)
        self._refresh_ports()

    def update_serial_info(self):
        port = self.ui.resist
        old = port.currentText()
        self._refresh_ports()
        self._set_resist_port(old)

    def _refresh_ports(self):
        self.ui.resist.clear()
        self.ports = [port.portName() for port in QSerialPortInfo.availablePorts()]
        if len(self.ports) == 0: return
        self.ui.resist.addItems(self.ports)

    def _set_resist_port(self, port):
        if port in self.ports:
            self.ui.resist.setCurrentText(port)
        else:
            self.ui.resist.setCurrentIndex(0)

    def get_devices(self):
        devices = {}
        for name, box in self.devices.items():
            addr = str()
            if isinstance(box, QtWidgets.QComboBox):
                addr = box.currentText()
            elif isinstance(box, QtWidgets.QLineEdit):
                addr = box.text()
            if addr: devices[name] = addr
        
        resist = self.ui.resist.currentText()
        if resist: devices['R'] = resist

        return devices

    def save(self):
        data = { name: box.text() for name, box in self.devices.items() }
        data['R'] = self.ui.resist.currentText()
        return data

    def load(self, data: dict):
        for i in range(1, 6):
            name = f'DMM{i}'
            box = self.devices[name]
            ip = data.get(name, f'192.168.31.{i}')
            box.setText(ip)

        for i in range(1, 3):
            name = f'Power{i}'
            box = self.devices[name]
            ip = data.get(name, f'192.168.31.1{i}')
            box.setText(ip)
            
        self.update_serial_info()
        resist = data.get('R', '')
        self._refresh_ports()
        self._set_resist_port(resist)
