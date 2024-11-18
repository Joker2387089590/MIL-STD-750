import pyvisa, time, re, math
from typing import Literal
from pyvisa.resources.tcpip import TCPIPInstrument
from pyvisa.constants import ResourceAttribute

class Meter:
    def __init__(self, ip: str, func: Literal['VOLTage', 'CURRent']):
        try:
            rm = pyvisa.ResourceManager()
            self.instr: TCPIPInstrument = rm.open_resource(f'TCPIP::{ip}::INSTR')
        except Exception as e:
            raise Exception(f'万用表 {ip} 连接失败') from e
        self.instr.set_visa_attribute(ResourceAttribute.timeout_value, 1_000)
        self.func = func
        self.instr.write('*RST')

    def reconfig(self):
        cmds = [
            'TRIGger:SOURce IMM',
            'TRIGger:COUNt 1',
            'SAMPle:COUNt 1',
            'VOLTage:NPLC 10',
            'CURRent:NPLC 10',
            f'FUNC "{self.func}"',
        ]
        if self.func == 'CURRent':
            cmds.append('CURRent:DC:RANGe 20mA')
        for cmd in cmds:
            self.instr.write(cmd)
            time.sleep(0.100)

    def reconfig_rear(self):
        self.instr.write('*RST')
        time.sleep(2.000)

        cmds = [
            'ROUTe:SCAN ON',
            'ROUTe:FUNCtion SCAN',
            'ROUTe:COUNt 1',
            'ROUTe:LIMIt:LOW 12',
            'ROUTe:LIMIt:HIGH 13',
            'ROUTe:CHANnel 12,ON,DCV,AUTO,FAST,1',
            'ROUTe:CHANnel 13,ON,DCI,AUTO,FAST,1',
        ]
        for cmd in cmds:
            self.instr.write(cmd)
            time.sleep(0.100)

    def disconnects(self):
        self.instr.close()

    data_points_pattern = re.compile(r'#(\d)(.*)')

    def initiate(self):
        self.instr.write(f'INIT')
    
    def fetch(self):
        end = time.time() + 3
        while time.time() < end:
            points = int(self.instr.query('DATA:POINts?'))
            if points <= 0:
                time.sleep(0.100)
                continue

            result = self.instr.query('R?')
            matches = re.match(self.data_points_pattern, result)
            assert matches
            count = int(matches[1])
            data = matches[2][count + 1:]
            datas = data.split(',')
            return float(datas[-1])
        raise Exception('万用表测量触发失败')

    def read_front(self) -> float:
        fail = time.time() + 10
        while time.time() < fail:
            self.instr.write(f'INIT')
            time.sleep(0.800)

            end = time.time() + 3
            while time.time() < end:
                # self.instr.write('*TRG')
                # time.sleep(0.400)

                points = int(self.instr.query('DATA:POINts?'))
                if points <= 0:
                    time.sleep(0.100)
                    continue

        assert False
        return math.nan

    route_data_pattern = re.compile(r'12:(.*?) VDC,13:(.*?) ADC')

    def read(self):
        self.instr.query('ROUTe:DATA:REMOve?')

        self.instr.write('ROUTe:STARt ON')
        end = time.time() + 3.000
        while True:
            time.sleep(0.200)
            if self.instr.query('ROUTe:STARt?').startswith('OFF'): break
            if time.time() > end: raise Exception('扫描超时')
        
        data = self.instr.query('ROUTe:DATA:REMOve?')
        matches = re.match(self.route_data_pattern, data)
        if not matches: raise Exception(f'读取结果失败: {data}')

        Vce = float(matches[1])
        Ic = float(matches[2])
        return Vce, Ic
    

