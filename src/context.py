import traceback, time, math, random
from typing import Literal
from dataclasses import dataclass, asdict
from contextlib import ExitStack
from PySide6.QtCore import QObject, Signal, Slot
from .resist import Resist
from .dmm import Meter
from .power import PowerCV

@dataclass
class Argument:
    type: Literal['NPN', 'PNP']
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
class NpnResult:
    Vc:  float = math.nan
    Ve:  float = math.nan
    Vce: float = math.nan
    Vbe: float = math.nan
    Vcb: float = math.nan
    Ic:  float = math.nan
    Ie:  float = math.nan
    R:   float = math.nan

@dataclass
class PnpResult:
    Vc:  float = math.nan
    Ve:  float = math.nan
    Vce: float = math.nan
    Vbc: float = math.nan
    Veb: float = math.nan
    Ic:  float = math.nan
    Ie:  float = math.nan
    R:   float = math.nan

def as_str(result):
    return '\n'.join(f'{key} = {value:.6f}' for key, value in asdict(result).items())

def direction(value, target):
    if value < target * 0.95:
        return -1
    elif value > target * 1.05:
        return 1
    else:
        return 0

class Context(QObject):
    stateChanged = Signal(str)
    deviceChanged = Signal(str, bool)
    npn_tested = Signal(NpnResult)
    pnp_tested = Signal(PnpResult)
    errorOccurred = Signal(str)

    DMM1: Meter
    DMM2: Meter
    DMM3: Meter
    DMM4: Meter
    DMM5: Meter
    Power1: PowerCV
    Power2: PowerCV
    R: Resist

    def _test_no_cache(self, V1: float, V2: float, output_time: float = 0.100):
        self.Power1.set_voltage(V1)
        self.Power2.set_voltage(V2)

        with self.Power1, self.Power2:
            # NOTE: 此处开始打开电源
            time.sleep(output_time)
            for dmm in [self.DMM1, self.DMM2, self.DMM3, self.DMM4, self.DMM5]:
                dmm.initiate()

        time.sleep(0.200)
            
        results = dict(
            DMM1=self.DMM1.fetch(),
            DMM2=self.DMM2.fetch(),
            DMM3=self.DMM3.fetch(),
            DMM4=self.DMM4.fetch(),
            DMM5=self.DMM5.fetch(),
            Power1=V1,
            Power2=V2,
            R=self._R,
        )
        return results

    def _test_npn(self, Vc: float, Ve: float):
        if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
        if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
        results = self._test_no_cache(Vc, Ve)
        xresult = NpnResult(
            Vc=results['Power1'],
            Ve=results['Power2'],
            Vce=results['DMM1'],
            Vbe=results['DMM2'],
            Vcb=results['DMM3'],
            Ic=results['DMM4'],
            Ie=results['DMM5'],
            R=results['R'],
        )
        print(f'[test:{time.time() - self.begin:.3f}s] {as_str(xresult)}')
        self.npn_tested.emit(xresult)
        return xresult.Vce, xresult.Ic
    
    def _test_pnp(self, Vc: float, Ve: float):
        if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
        if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
        results = self._test_no_cache(Ve, Vc)
        xresult = PnpResult(
            Vc=results['Power2'],
            Ve=results['Power1'],
            Vce=-results['DMM1'],
            Vbc=-results['DMM2'],
            Veb=-results['DMM3'],
            Ic=results['DMM5'],
            Ie=results['DMM4'],
            R=results['R'],
        )
        print(f'[test:{time.time() - self.begin:.3f}s] {as_str(xresult)}')
        self.pnp_tested.emit(xresult)
        return xresult.Vce, xresult.Ic

    @Slot()
    def run(self, arg: Argument, dev: dict):
        try:
            self.stateChanged.emit('is_running')
            self.arg = arg
            self.DMM1 = Meter(dev['DMM1'], 'VOLTage')
            self.DMM2 = Meter(dev['DMM2'], 'VOLTage')
            self.DMM3 = Meter(dev['DMM3'], 'VOLTage')
            self.DMM4 = Meter(dev['DMM4'], 'CURRent')
            self.DMM5 = Meter(dev['DMM5'], 'CURRent')
            self.Power1 = PowerCV(dev['Power1'])
            self.Power2 = PowerCV(dev['Power2'])
            self.R = Resist(dev['R'])
            self.run_npn()
            self.stateChanged.emit('pass')
        except Exception as e:
            traceback.print_exc()
            self.errorOccurred.emit(str(e))
            self.stateChanged.emit('fail')
        finally:
            self.DMM1.disconnects()
            self.DMM2.disconnects()
            self.DMM3.disconnects()
            self.DMM4.disconnects()
            self.DMM5.disconnects()
            self.Power1.disconnects()
            self.Power2.disconnects()
            self.R.disconnects()

    def reconfig(self):
        self.stateChanged.emit('初始化仪器')
        for key in ['DMM1', 'DMM2', 'DMM3', 'DMM4', 'DMM5', 'Power1', 'Power2']:
            if hasattr(self, key):
                getattr(self, key).reconfig()
        
    def setup_resist(self):
        # 尝试电阻的等级
        Req = self.arg.Vce / self.arg.Ic
        self.R.set_value(Req)
        self._R = Req

    def run_npn(self):
        def stage1():
            # 匹配 (Vce, 0)
            self.stateChanged.emit('第1步: 匹配 (Vce, 0)')
            Vc = self.arg.Vce / 2
            Ve = self.arg.Vce / 2
            while True:
                Vce, Ic = self._test_npn(Vc, Ve)
                match direction(Vce, self.arg.Vce):
                    case -1:
                        print(f'adjust Vce lower', flush=True)
                        Vc += 1
                        continue
                    case 0:
                        print(f'match 1')
                        return Vc, Ve
                    case 1:
                        print(f'adjust Vce upper', flush=True)
                        Vc -= 0.1
                        continue

        def stage2(Vc: float, Ve: float):
            # 匹配 (Vce, 0) => (Vce, Ic_mid)
            self.stateChanged.emit('第2步: 匹配 (Vce, Ic_mid)')
            while True:
                # logY = k logX + b
                # log(Y / e^b) = log (X^k)
                # Ic / e^b = Vce^k
                # Vce / Ic 
                Vce, Ic = self._test_npn(Vc, Ve)

                match direction(Vce, self.arg.Vce):
                    case -1:
                        print(f'adjust Vce lower', flush=True)
                        Vc -= (Vce - self.arg.Vce)
                        continue
                    case 1:
                        print(f'adjust Vce upper', flush=True)
                        Vc -= 0.1
                        Ve += 0.1
                        continue
                
                match direction(Ic, self.arg.Ic_mid):
                    case -1:
                        print(f'adjust Ic lower', flush=True)
                        Vc += 1
                        Ve += 1
                        continue
                    case 0:
                        print(f'-- match 2')
                        return Vc, Ve
                    case 1:
                        print(f'adjust Ic upper', flush=True)
                        Ve += 0.1
                        continue

        def stage3(Vc: float, Ve: float):
            # 匹配 (Vce, Ic_mid) => (Vce_mid, Ic)
            while True:
                Vce, Ic = self._test_npn(Vc, Ve)

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

        def stage4(Vc: float, Ve: float):
            # 匹配 (Vce_mid, Ic) => (0, Ic)
            while True:
                if Vc < 0:
                    print('-- match 3')
                    break

                Vce, Ic = self._test_npn(Vc, Ve)
                
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

        self.begin = time.time()
        self.reconfig()
        self.Power1.set_limit_current(self.arg.Ic * 1.5)
        self.Power2.set_limit_current(self.arg.Ic * 1.5)
        self.setup_resist()
        Vc, Ve = stage1()
        Vc, Ve = stage2(Vc, Ve)
        Vc, Ve = stage3(Vc, Ve)
        stage4(Vc, Ve)

    def run_pnp(self):
        self.begin
    
    @Slot()
    def pause(self):
        ...

    @Slot()
    def abort(self):
        ...
