import pyvisa
from pyvisa.resources.tcpip import TCPIPInstrument

class Power:
    def __init__(self) -> None:
        rm = pyvisa.ResourceManager()
        self.instr: TCPIPInstrument = rm.open_resource('TCPIP::192.168.31.49::INSTR')
        self.instr.write(':SYSTem:REMote')

    def set_cv_mode(self, protect: float | None = None):
        cmds = [
            'SOURce:FUNCtion VOLTage',
            'SOURce:FUNCtion:MODE FIXed',
        ]
        if protect is None:
            cmds.append('VOLT:PROT:STATE OFF')
        else:
            cmds.append('VOLT:PROT:STATE ON')
            cmds.append(f'VOLT:PROT {protect}')
        
        cmds.append('*OPC')
        for cmd in cmds: self.instr.write(cmd)

    def set_voltage(self, output: float):
        self.instr.write(f'VOLT {output}')

    def set_output_state(self, state: bool):
        self.instr.query(f"OUTPut:STATe {'ON' if state else 'OFF'};*OPC?")
    
    def clear_protection(self):
        self.instr.write('OUTPut:PROTection:CLEar')
