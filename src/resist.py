from PySide6.QtCore import QObject
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

class Resist(QObject):
    def __init__(self, port: QSerialPortInfo, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.port = QSerialPort(port, self)
    
    def open(self) -> bool:
        return self.port.open(QSerialPort.OpenModeFlag.ReadWrite)

    