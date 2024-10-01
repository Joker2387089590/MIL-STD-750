import sys
from PySide6.QtCore import QObject, Slot
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

class Resist(QObject):
    def __init__(self, info: QSerialPortInfo, parent: QObject | None = None) -> None:
        super().__init__(parent)

        port = QSerialPort(info, self)
        port.setBaudRate(4800)
        if not port.open(QSerialPort.OpenModeFlag.ReadWrite):
            port.deleteLater()
            raise Exception(port.errorString())
        
        port.readyRead.connect(self.read_all)
        self.port = port

    def disconnects(self):
        self.port.close()
        self.deleteLater()

    @Slot()
    def read_all(self):
        while self.port.bytesAvailable() >= 6:
            response = self.port.read(6).toHex(ord(' ')).toUpper()
            print('[resist]', 'read_all:', response, file=sys.stderr)

    def write(self, states: str):
        data = bytes.fromhex(f'AA {states} 55')
        if len(data) != 6: 
            print('[resist]', f'invalid states:', states, file=sys.stderr)
            return
        self.port.write(data)

    def set_value(self, res: float):
        ...
