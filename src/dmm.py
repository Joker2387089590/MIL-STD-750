import pyvisa
from pyvisa.resources.tcpip import TCPIPInstrument

class Meter:
    def __init__(self, ip: str = '192.168.31.129'):
        rm = pyvisa.ResourceManager()
        self.instr: TCPIPInstrument = rm.open_resource(f'TCPIP::{ip}::INSTR')
        self.instr.write('TRIGger:SOURce BUS')

    def disconnects(self):
        self.instr.close()

    def set_function(self, func: str):
        self.instr.write(f'FUNC "{func}"')

    def trigger(self):
        self.instr.write('*TRG')

    def read(self) -> float:
        return float(self.instr.query('READ?'))
