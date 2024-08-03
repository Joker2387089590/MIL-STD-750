import pyvisa
from pyvisa.resources.tcpip import TCPIPInstrument

class Meter:
    def __init__(self):
        rm = pyvisa.ResourceManager()
        self.instr: TCPIPInstrument = rm.open_resource('TCPIP::192.168.31.129::INSTR')
        self.instr.write('TRIGger:SOURce BUS')

    def set_function(self, func: str):
        self.instr.write(f'FUNC: "{func}"')

    def trigger(self):
        self.instr.write('*TRG')


