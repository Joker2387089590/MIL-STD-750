import traceback, math
from dataclasses import dataclass
from contextlib import ExitStack
from PySide6.QtCore import QObject, Signal, Slot
from .resist import Resist
from .dmm import Meter
from .power import PowerCV

@dataclass
class Argument:
    Vce: float
    Ic: float
    Pmax: float
    hFE: float
    Vc_max: float
    Ve_max: float

@dataclass
class State:
    Vb: float
    Vc: float

class Device(QObject):
    def __init__(self, resist, dmm, power_vc, power_ve) -> None:
        super().__init__(None)
        with ExitStack() as stack:
            self.resist = Resist(resist, self); stack.callback(self.resist.disconnects)
            self.dmm = Meter(dmm); stack.callback(self.dmm.disconnects)
            self.power_vc = PowerCV(power_vc); stack.callback(self.power_vc.disconnects)
            self.power_ve = PowerCV(power_ve); stack.callback(self.power_ve.disconnects)
            self._disconnects = stack.pop_all()
    
    def disconnects(self):
        self._disconnects.close()
        self.deleteLater()

class Context(QObject):
    paused = Signal()
    pointTested = Signal(float, float, float, float) # Vc, Ve, Vce, Ic

    def __init__(self, arg: Argument, dev: Device) -> None:
        super().__init__(None)
        self.arg = arg
        self.dev = dev
        self.mapping: dict[tuple[float, float], tuple[float, float]] = {}
        
    def _test_no_cache(self, Vc: float, Ve: float):
        if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
        if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
        self.dev.power_vc.set_voltage(Vc)
        self.dev.power_ve.set_voltage(Ve)
        with self.dev.power_vc, self.dev.power_ve:
            return self.dev.dmm.read_dc_volt(), self.dev.dmm.read_dc_current()

    def _test(self, Vc: float, Ve: float):
        pair = (Vc, Ve)
        if pair in self.mapping: return self.mapping[pair]
        Vce, Ic = self._test_no_cache(Vc, Ve)
        self.mapping[pair] = (Vce, Ic)
        self.pointTested.emit(Vc, Ve, Vce, Ic)

    @Slot()
    def run(self):
        try:
            self.dev.power_vc.reconfig()
            self.dev.power_ve.reconfig()
            self.dev.dmm.reconfig()

            self.dev.power_vc.set_limit_current(self.arg.Ic * 1.5)
            self.dev.power_ve.set_limit_current(self.arg.Ic * 1.5)

            # 尝试电阻的等级
            Req = self.arg.hFE * self.arg.Vce / self.arg.Ic
            Vc = self.arg.Vce / 2
            Ve = self.arg.Vce / 2
            while True:
                self.dev.resist.set_value(Req)
                Vce, Ic = self._test_no_cache(Vc, Ve)
                if Ic < self.arg.Ic: break
                if Req > 1: 
                    Req /= 10
                else:
                    Vc -= 0.1 * self.arg.Vce
                    Ve -= 0.1 * self.arg.Vce

            # 匹配 Vce
            exp_step_Vc = int(math.log(Vce, 10)) - 1
            step_Vc = 10 ** max(exp_step_Vc, -2)
            while True:
                Vce, Ic = self._test(Vc, Ve)
                tolerance = 0.05 * self.arg.Vce
                if Vce - self.arg.Vce > -tolerance: break
                Vc += step_Vc

            step_V = ...

        except KeyboardInterrupt:
            pass
        except:
            traceback.print_exc()
        finally:
            pass

    @Slot()
    def pause(self):
        ...

    @Slot()
    def stop(self):
        ...
