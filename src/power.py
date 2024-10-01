import pyvisa
from pyvisa.resources.tcpip import TCPIPInstrument

class Power:
    def __init__(self, ip: str) -> None:
        rm = pyvisa.ResourceManager()
        self.instr: TCPIPInstrument = rm.open_resource(f'TCPIP::{ip}::INSTR')
        self.instr.write('VOLT:PROT 200')
        self.instr.write('VOLT:PROT:STATE ON')

    def reconfig(self):
        self.instr.write(':SYSTem:REMote')
        self.instr.write('*RST')

    def disconnects(self):
        self.instr.close()

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

    def __enter__(self):
        self.set_output_state(True)

    def __exit__(self, *exception):
        self.set_output_state(False)
    
    def clear_protection(self):
        self.instr.write('OUTPut:PROTection:CLEar')

    def set_current_protection(self, current: float):
        self.instr.write(f'CURRent:PROTection {current}')
        self.instr.write('CURRent:PROTection:STATE ON')

    def config_arb(self, volt: float, time: float):
        cmds = [
            'TRIGger:ARB:SOURce BUS',
            'FUNCtion:MODE LIST',
            'ARB:FUNCtion:SHAPe PULSe',
            'ARB:COUNt 1',
            f'ARB:PULSe:START:LEVel {volt}',
            f'ARB:PULSe:START:TIME 0',
            f'ARB:PULSe:TOP:LEVel {volt}',
            f'ARB:PULSe:TOP:TIME {time}',
            f'ARB:PULSe:STOP:LEVel 0',
        ]
        for cmd in cmds:
            self.instr.write(cmd)
