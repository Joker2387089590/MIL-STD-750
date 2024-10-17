import pyvisa
from pyvisa.resources.tcpip import TCPIPInstrument

class Power:
    def __init__(self, ip):
        rm = pyvisa.ResourceManager()
        self.instr: TCPIPInstrument = rm.open_resource(f'TCPIP::{ip}::INSTR')

    def reconfig(self):
        cmds = [':SYSTem:REMote', '*RST', '*WAI']
        for cmd in cmds: self.instr.write(cmd)

    def disconnects(self):
        self.instr.close()

    def set_output_state(self, state: bool):
        self.instr.query(f"OUTPut:STATe {'ON' if state else 'OFF'};*OPC?")

    def __enter__(self):
        self.set_output_state(True)

    def __exit__(self, *exception):
        self.set_output_state(False)
    
    def clear_protection(self):
        self.instr.write('OUTPut:PROTection:CLEar')

class PowerCC(Power):
    def reconfig(self):
        super().reconfig()
        cmds = [
            'SOURce:FUNCtion CURRent',
            'SOURce:FUNCtion:MODE FIXed',
            '*WAI',
        ]
        for cmd in cmds: self.instr.write(cmd)

    def set_current(self, curr: float):
        self.instr.write(f'CURRent {curr}')

    def set_limit_voltage(self, volt: float):
        self.instr.write(f'VOLTage:LIMit:POSitive {volt}')

class PowerCV(Power):
    def reconfig(self):
        super().reconfig()
        cmds = [
            'SOURce:FUNCtion VOLTage',
            'SOURce:FUNCtion:MODE FIXed',
            '*WAI',
        ]
        for cmd in cmds: self.instr.write(cmd)

    def set_voltage(self, volt: float):
        self.instr.write(f'VOLTage {volt}')
    
    def set_limit_current(self, curr: float):
        self.instr.write(f'CURRent:LIMit:POSitive {curr}')
