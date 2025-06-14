from __future__ import annotations
import pyvisa, time
from pyvisa.resources.tcpip import TCPIPInstrument

class _Remote:
    def __init__(self, power: Power):
        self.power = power

    def __enter__(self):
        if self.power._fake: return
        self.power.instr.write(':SYSTem:REMote')

    def __exit__(self, *exception):
        if self.power._fake: return
        try:
            self.power.instr.write(':SYSTem:LOCal')
        except:
            pass

class _Output:
    def __init__(self, power: Power):
        self.power = power
    
    def __enter__(self):
        if self.power._fake: return
        self.power.instr.query('OUTPut:STATe ON;*OPC?')
    
    def __exit__(self):
        if self.power._fake: return
        try:
            self.power.instr.write('OUTPut:STATe OFF')
        except:
            pass

class Power:
    def __init__(self, ip, fake: bool = False):
        self._fake = fake
        if fake: return
        try:
            rm = pyvisa.ResourceManager()
            instr = rm.open_resource(f'TCPIP::{ip}::INSTR')
            assert isinstance(instr, TCPIPInstrument)
            self.instr = instr 
        except Exception as e:
            raise Exception(f'电源 {ip} 连接失败') from e

    def reconfig(self):
        if self._fake: return
        cmds = ['*RST', '*WAI']
        for cmd in cmds: 
            self.instr.write(cmd)
            time.sleep(0.100)

    def disconnects(self):
        if self._fake: return
        self.instr.close()

    def set_output_state(self, state: bool):
        if self._fake: return
        self.instr.query(f"OUTPut:STATe {'ON' if state else 'OFF'};*OPC?")

    def __enter__(self):
        if self._fake: return
        self.set_output_state(True)

    def __exit__(self, *exception):
        if self._fake: return
        self.set_output_state(False)

    def remote(self):
        return _Remote(self)
    
    def output(self):
        return _Output(self)
    
    def clear_protection(self):
        if self._fake: return
        self.instr.write('OUTPut:PROTection:CLEar')

    def config_arb(self, volt: float, time: float):
        if self._fake: return
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
        if self._fake: return
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
        if self._fake: return
        super().reconfig()
        cmds = [
            'SOURce:FUNCtion CURRent',
            'SOURce:FUNCtion:MODE FIXed',
            '*WAI',
        ]
        for cmd in cmds: self.instr.write(cmd)

    def set_current(self, curr: float):
        if self._fake: return
        self.instr.write(f'CURRent {curr}')

    def set_limit_voltage(self, volt: float):
        if self._fake: return
        self.instr.write(f'VOLTage:LIMit:POSitive {volt}')

class PowerCV(Power):
    def reconfig(self):
        if self._fake: return
        super().reconfig()
        cmds = [
            'SOURce:FUNCtion VOLTage',
            'SOURce:FUNCtion:MODE FIXed',
            '*WAI',
        ]
        for cmd in cmds: self.instr.write(cmd)

    def set_voltage(self, volt: float):
        if self._fake: return
        self.instr.write(f'VOLTage {volt}')
    
    def set_limit_current(self, curr: float):
        if self._fake: return
        xcurr = min(curr, 24)
        self.instr.write(f'CURRent:LIMit:POSitive {xcurr}')
