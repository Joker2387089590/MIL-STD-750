import sys, math, logging
from PySide6.QtCore import QObject
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

_logger = logging.getLogger(__name__)

def _resist_bit(res: float) -> int:
    exp = max(math.floor(math.log10(res)), -1)
    return (~(1 << (exp + 1))) & 0xFF

class Resist(QObject):
    def __init__(self, info: QSerialPortInfo, parent: QObject | None = None) -> None:
        super().__init__(parent)

        port = QSerialPort(info, self)
        port.setBaudRate(9600)
        if not port.open(QSerialPort.OpenModeFlag.ReadWrite):
            port.deleteLater()
            raise Exception(port.errorString())
        
        # port.readyRead.connect(self.read_all)
        self.port = port
        self.res1 = 0xFF
        self.res2 = 0xFF

    def disconnects(self):
        self.port.close()
        self.deleteLater()

    def _apply(self):
        cmd = bytes([0xAA, self.res1, self.res2, 0xFF, 0xFF, 0x55])
        xcmd = cmd.hex(" ")
        _logger.debug(f'try apply: {xcmd}')
        self.port.write(cmd)
        if self.port.waitForReadyRead(3000):
            _logger.info(f'apply: {xcmd} -> {self.port.readAll().toHex(ord(b" "))}')
        else:
            _logger.error(f'apply fail: {xcmd}')

    def reconfig(self):
        self.res1 = self.res2 = 0xFF
        self._apply()

    def write(self, states: str):
        data = bytes.fromhex(f'AA {states} 55')
        if len(data) != 6:
            print('[resist]', f'invalid states:', states, file=sys.stderr)
            return
        self.port.write(data)

    def set_resist1(self, res1: float):
        self.res1 = _resist_bit(res1)
        self._apply()

    def set_resist2(self, res2: float):
        self.res2 = _resist_bit(res2)
        self._apply()

    def set_resists(self, res: float):
        self.res1 = self.res2 = _resist_bit(res)
        self._apply()

