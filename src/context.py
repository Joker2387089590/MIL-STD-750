import traceback, time
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

    @property
    def Ic_mid(self): return self.Pmax / self.Vce

    @property
    def Vce_mid(self): return self.Pmax / self.Ic

@dataclass
class State:
    Vb: float
    Vc: float

def direction(value, target):
    if value < target * 0.95:
        return -1
    elif value > target * 1.05:
        return 1
    else:
        return 0

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
    stopped = Signal()
    pointTested = Signal(float, float, float, float) # Vc, Ve, Vce, Ic

    def __init__(self, arg: Argument, dev: Device) -> None:
        super().__init__(None)
        self.arg = arg
        self.dev = dev
        
    def _test_no_cache(self, Vc: float, Ve: float):
        if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
        if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
        self.dev.power_vc.set_voltage(Vc)
        self.dev.power_ve.set_voltage(Ve)
        time.sleep(0.100)
        Vce, Ic = self.dev.dmm.read()
        print(f'[test:{time.time() - self.begin:.3f}s] {Vc = :.3f}V, {Ve = :.3f}V, {Vce = :.3f}V, Ic = {Ic * 1e3:.3f}mA')
        return Vce, Ic

    def _test(self, Vc: float, Ve: float):
        Vce, Ic = self._test_no_cache(Vc, Ve)
        self.pointTested.emit(Vc, Ve, Vce, Ic)
        return Vce, Ic

    @Slot()
    def run(self):
        try:
            self.begin = time.time()

            self.dev.power_vc.reconfig()
            self.dev.power_ve.reconfig()
            self.dev.dmm.reconfig()

            self.dev.power_vc.set_limit_current(self.arg.Ic * 1.5)
            self.dev.power_ve.set_limit_current(self.arg.Ic * 1.5)

            with self.dev.power_vc, self.dev.power_ve:
                Vc, Ve = self.stage1()
                Vc, Ve = self.stage2(Vc, Ve)
                Vc, Ve = self.stage3(Vc, Ve)
                self.stage4(Vc, Ve)
        except KeyboardInterrupt:
            pass
        except:
            traceback.print_exc()
        finally:
            self.stopped.emit()

    def setup_resist(self):
        # 尝试电阻的等级
        Req = self.arg.hFE * self.arg.Vce / self.arg.Ic * 0.1
        self.dev.resist.set_value(Req)

    def stage1(self):
        # 匹配 (Vce, 0)
        Vc = self.arg.Vce / 2
        Ve = self.arg.Vce / 2
        while True:
            Vce, Ic = self._test(Vc, Ve)
            match direction(Vce, self.arg.Vce):
                case -1:
                    print(f'adjust Vce lower', flush=True)
                    Vc += 0.1
                    continue
                case 0:
                    print(f'match 1')
                    return Vc, Ve
                case 1:
                    print(f'adjust Vce upper', flush=True)
                    Vc -= 0.01
                    continue

    def stage2(self, Vc: float, Ve: float):
        # 匹配 (Vce, 0) => (Vce, Ic_mid)
        while True:
            Vce, Ic = self._test(Vc, Ve)

            match direction(Vce, self.arg.Vce):
                case -1:
                    print(f'adjust Vce lower', flush=True)
                    Vc -= (Vce - self.arg.Vce)
                    continue
                case 1:
                    print(f'adjust Vce upper', flush=True)
                    Vc -= 0.01
                    Ve += 0.01
                    continue
            
            match direction(Ic, self.arg.Ic_mid):
                case -1:
                    print(f'adjust Ic lower', flush=True)
                    Vc += 0.1
                    Ve += 0.1
                    continue
                case 0:
                    print(f'-- match 2')
                    return Vc, Ve
                case 1:
                    print(f'adjust Ic upper', flush=True)
                    Vc -= 0.01
                    continue

    def stage3(self, Vc: float, Ve: float):
        # 匹配 (Vce, Ic_mid) => (Vce_mid, Ic)
        while True:
            Vce, Ic = self._test(Vc, Ve)

            if direction(Ic, self.arg.Ic) > 0:
                print(f'-- match 3', flush=True)
                return Vc, Ve

            match direction(Vce * Ic, self.arg.Pmax):
                case -1:
                    print(f'adjust Pmax lower', flush=True)
                    Vc += 0.01
                    Ve += 0.01
                    continue
                case 0:
                    print(f'adjust Pmax mid', flush=True)
                    Ve += 0.1
                    continue
                case 1:
                    print(f'adjust Pmax upper', flush=True)
                    Vc -= 0.01
                    continue

    def stage4(self, Vc: float, Ve: float):
        # 匹配 (Vce_mid, Ic) => (0, Ic)
        while True:
            if Vc < 0:
                print('-- match 3')
                break

            Vce, Ic = self._test(Vc, Ve)
            
            if Vce < 0.01:
                print('-- match 4')
                break

            match direction(Ic, self.arg.Ic):
                case -1:
                    print(f'adjust Ic lower', flush=True)
                    Vc += 0.01
                    Ve += 0.01
                    continue
                case 0:
                    print(f'adjust Ic mid', flush=True)
                    Vc -= 0.01
                    continue
                case 1:
                    print(f'adjust Ic upper', flush=True)
                    Ve -= 0.01
                    continue

    @Slot()
    def pause(self):
        ...

    @Slot()
    def stop(self):
        ...
