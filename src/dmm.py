import pyvisa, time, re, math
from typing import TypeVar
from pyvisa.resources.tcpip import TCPIPInstrument
from pyvisa.constants import ResourceAttribute

class DCI:
    def __init__(self, instr: TCPIPInstrument): ...
    def measure(self) -> float: ...

class DCV:
    def __init__(self, instr: TCPIPInstrument): ...
    def measure(self) -> float: ...

class RearChannel:
    def __init__(self, instr: TCPIPInstrument, channel: int):
        pass

    def measure(): ...

_M = TypeVar('_M')
   
class Meter:
    def __init__(self, ip: str = '192.168.31.129'):
        rm = pyvisa.ResourceManager()
        self.instr: TCPIPInstrument = rm.open_resource(f'TCPIP::{ip}::INSTR')
        self.instr.set_visa_attribute(ResourceAttribute.timeout_value, 1_000)

    def reconfig(self):
        self.instr.write('*RST')
        time.sleep(2.000)

        cmds = [
            'TRIGger:SOURce IMM',
            'TRIGger:COUNt 1',
            'SAMPle:COUNt 1',
            'VOLTage:NPLC 10',
            'CURRent:NPLC 10',
            
        ]
        for cmd in cmds:
            self.instr.write(cmd)
            time.sleep(0.200)

    def disconnects(self):
        self.instr.close()

    def read(self, func: str) -> float:
        fail = time.time() + 10
        while time.time() < fail:
            self.instr.write(f'{func};INIT')
            time.sleep(0.800)

            end = time.time() + 3
            while time.time() < end:
                # self.instr.write('*TRG')
                # time.sleep(0.400)

                points = int(self.instr.query('DATA:POINts?'))
                if points <= 0:
                    time.sleep(0.100)
                    continue

                result = self.instr.query('R?')
                r1 = re.compile(r'#(\d)(.*)')
                matches = re.match(r1, result)
                assert matches
                count = int(matches[1])
                data = matches[2][count + 1:]
                datas = data.split(',')
                return float(datas[-1])
        assert False
        return math.nan
    
    def read2(self, func: str) -> float:
        self.instr.write(func)
        return float(self.instr.query('READ?'))
    
    def read_dc_volt(self):
        return self.read2('FUNC "VOLTage"')
    
    def read_dc_current(self):
        return self.read2('FUNC "CURRent"')
