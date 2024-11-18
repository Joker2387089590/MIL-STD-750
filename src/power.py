import pyvisa, time
from pyvisa.resources.tcpip import TCPIPInstrument

class Power:
    def __init__(self, ip):
        try:
            rm = pyvisa.ResourceManager()
            self.instr: TCPIPInstrument = rm.open_resource(f'TCPIP::{ip}::INSTR')
        except Exception as e:
            raise Exception(f'电源 {ip} 连接失败') from e

    def reconfig(self):
        cmds = [':SYSTem:REMote', '*RST', '*WAI']
        for cmd in cmds: 
            self.instr.write(cmd)
            time.sleep(0.100)

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

    def config_arb(self, volt: float, time: float):
        cmds = [
            'FUNCtion:MODE LIST',
            'ARB:FUNCtion:SHAPe PULSe',
            'ARB:COUNt 1',
            'ARB:FUNCtion:TYPE VOLTage',
            'ARB:PULSe:START:LEVel MIN',
            'ARB:PULSe:START:TIME MIN',
            f'ARB:PULSe:TOP:LEVel {volt}',
            f'ARB:PULSe:TOP:TIME {time}',
            'ARB:PULSe:END:TIME MIN',
            'ARB:SAVE 1',
        ]
        for cmd in cmds:
            self.instr.write(cmd)
    
    def start_arb(self):
        cmds = [
            'TRIGger:ARB:SOURce BUS',
            'ARB:RECALL 1',
            'OUTPut 1',
            'INITiate:ARB',
            'TRIGger:ARB',
        ]
        for cmd in cmds:
            self.instr.write(cmd)

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
