from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Qt
from PySide6.QtSerialPort import QSerialPortInfo
from ..types import Devices
from .device_ui import Ui_DevicePanel

class DevicePanel(QtWidgets.QScrollArea):
    connectRequested = Signal(str)
    disconnectRequested = Signal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.setWidgetResizable(True)

        w = QtWidgets.QWidget(self)
        self.ui = Ui_DevicePanel()
        self.ui.setupUi(w)
        self.setWidget(w)

        self.devices: dict[str, QtWidgets.QLineEdit] = {}
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
            ip = QtWidgets.QLineEdit(w)
            self.ui.grid.addWidget(QtWidgets.QLabel(name, w), row, 0, Qt.AlignmentFlag.AlignCenter)
            self.ui.grid.addWidget(QtWidgets.QLabel(model, w), row, 1, Qt.AlignmentFlag.AlignCenter)
            self.ui.grid.addWidget(QtWidgets.QLabel(npn, w), row, 2, Qt.AlignmentFlag.AlignCenter)
            self.ui.grid.addWidget(QtWidgets.QLabel(pnp, w), row, 3, Qt.AlignmentFlag.AlignCenter)
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

        self.ports = []
        for info in QSerialPortInfo.availablePorts():
            if info.description() == 'USB Serial Port':
                self.ports.append(info.portName())

        if len(self.ports) == 0: return
        self.ui.resist.addItems(self.ports)

    def _set_resist_port(self, port):
        if port in self.ports:
            self.ui.resist.setCurrentText(port)
        else:
            self.ui.resist.setCurrentText('COM3')

    def get_devices(self) -> Devices:
        return Devices(
            dmms = [self.devices[f'DMM{i}'].text() for i in range(1, 6)],
            power1 = self.devices['Power1'].text(),
            power2 = self.devices['Power2'].text(),
            resist = self.ui.resist.currentText(),
        )

    def save(self):
        data = { name: box.text() for name, box in self.devices.items() }
        data['R'] = self.ui.resist.currentText()
        return data

    def load(self, data: dict):
        if not isinstance(data, dict): data = {}

        for i in range(1, 6):
            name = f'DMM{i}'
            box = self.devices[name]
            ip = data.get(name, f'192.168.31.{i}')
            box.setText(ip)

        for i in range(1, 3):
            name = f'Power{i}'
            box = self.devices[name]
            ip = data.get(name, f'192.168.2{i}.1')
            box.setText(ip)
            
        self.update_serial_info()
        resist = data.get('R', 'COM3')
        self._refresh_ports()
        self._set_resist_port(resist)
