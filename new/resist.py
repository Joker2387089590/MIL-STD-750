import time, math, logging
from PySide6.QtCore import QObject
from PySide6.QtSerialPort import QSerialPort, QSerialPortInfo

log = logging.getLogger(__name__)

def ohm_to_float(ohm: str):
    return float(ohm.replace('k', 'e3'))

values = {
    0: '0',
    1: '1',
    10: '10',
    100: '100',
    1e3: '1k',
    10e3: '10k',
    100e3: '100k'
}

# TODO: 通过压降计算合适的电阻档位，让电源调节精度提高
def _resist_bit(res: float | str):
    if isinstance(res, str):
        res = ohm_to_float(res)
        if res > 0.5:
            exp = math.floor(math.log10(res))
        else:
            exp = -1
    elif isinstance(res, float):
        vexp = math.ceil(math.log10(res)) - 1
        exp = int(min(max(vexp, -1), 5)) - 1
    else:
        assert False, f'res type error: {res}'

    value = int(10 ** exp) if exp >= 0 else 0
    bits = (~(1 << (exp + 1))) & 0xFF
    return values[value], bits

class Resist(QObject):
    def __init__(self, info: str, parent: QObject | None = None) -> None:
        super().__init__(parent)

        port = QSerialPort(info, self)
        port.setBaudRate(9600)
        if not port.open(QSerialPort.OpenModeFlag.ReadWrite):
            port.deleteLater()
            raise Exception(port.errorString())
        
        self.port = port
        self.res1 = 0xFF
        self.res2 = 0xFF

    def disconnects(self):
        self.port.close()
        self.deleteLater()

    def _apply(self):
        if self.port.bytesAvailable(): self.port.readAll()
        cmd = bytes([0xAA, self.res1, self.res2, 0xFF, 0xFF, 0x55])
        xcmd = cmd.hex(" ")
        log.debug(f'try apply: {xcmd}')
        for _ in range(3):
            self.port.write(cmd)
            if self.port.waitForReadyRead(1000):
                response = self.port.readAll()
                if not response.contains(cmd):
                    log.warning(f'回复不匹配: {response}')
                return True
            time.sleep(0.200)
        return False

    def reconfig(self):
        self.res1 = self.res2 = 0xFF
        success = self._apply()
        if not success: raise Exception('重置电阻箱失败')
        log.info('重置电阻箱')

    def set_resist1(self, res1: float | str):
        value, self.res1 = _resist_bit(res1)
        if not self._apply():
            raise Exception(f'设置通道一为 {value} 失败')
        log.info(f'设置通道一为 {value}')
        return value

    def set_resist2(self, res2: float | str):
        value, self.res2 = _resist_bit(res2)
        if not self._apply():
            raise Exception(f'设置通道二为 {value} 失败')
        log.info(f'设置通道二为 {value}')
        return value

    def set_resists(self, res1: float | str, res2: float | str):
        value1, bits1 = _resist_bit(res1)
        value2, bits2 = _resist_bit(res2)
        self.res1 = bits1
        self.res2 = bits2
        if not self._apply():
            raise Exception(f'设置通道一为 {value1}，通道二为 {value2} 失败')
        log.info(f'设置电阻箱通道一为 {value1}')
        log.info(f'设置电阻箱通道二为 {value2}')
        return value1, value2
