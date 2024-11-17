import traceback, time, math
from typing import Literal
from dataclasses import dataclass, asdict
from contextlib import ExitStack
from PySide6.QtCore import QObject, Signal, Slot, QMutex
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
    return ', '.join(f'{key}={value:.6f}' for key, value in asdict(result).items())

def direction(value, target, range = 0.05):
    if value < target * (1 - range):
        return -1
    elif value > target * (1 + range):
        return 1
    else:
        return 0

class Context(QObject):
    stateChanged = Signal(str)
    deviceChanged = Signal(str, bool)
    npn_tested = Signal(NpnResult)
    pnp_tested = Signal(PnpResult)
    errorOccurred = Signal(str)
    test_point_matched = Signal(float, float, float, float)

    DMM1: Meter
    DMM2: Meter
    DMM3: Meter
    DMM4: Meter
    DMM5: Meter
    Power1: PowerCV
    Power2: PowerCV
    R: Resist

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mutex = QMutex()
        self._paused = False

    def _test_no_cache(self, V1: float, V2: float, output_time: float = 0.100):
        with ExitStack() as stack:
            self._mutex.lock()
            stack.callback(self._mutex.unlock)
            if self._paused: raise Exception('终止测试')

        self.Power1.set_voltage(V1)
        self.Power2.set_voltage(V2)

        with self.Power1, self.Power2:
            # NOTE: 此处开始打开电源
            time.sleep(0.050)
            for dmm in [self.DMM1, self.DMM2, self.DMM3, self.DMM4, self.DMM5]:
                dmm.initiate()
            time.sleep(0.550)

        # time.sleep(0.300)

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
        if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
        if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')
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
            self._paused = False
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
            self.begin = time.time()
            self.run_npn()
            # self.run_fake()
            self.stateChanged.emit('pass')
        except Exception as e:
            traceback.print_exc()
            self.errorOccurred.emit(str(e))
            self.stateChanged.emit('fail')
        finally:
            if hasattr(self, 'DMM1'): self.DMM1.disconnects(); del self.DMM1
            if hasattr(self, 'DMM2'): self.DMM2.disconnects(); del self.DMM2
            if hasattr(self, 'DMM3'): self.DMM3.disconnects(); del self.DMM3
            if hasattr(self, 'DMM4'): self.DMM4.disconnects(); del self.DMM4
            if hasattr(self, 'DMM5'): self.DMM5.disconnects(); del self.DMM5
            if hasattr(self, 'Power1'): self.Power1.disconnects(); del self.Power1
            if hasattr(self, 'Power2'): self.Power2.disconnects(); del self.Power2
            if hasattr(self, 'R'): self.R.disconnects(); del self.R

    def reconfig(self):
        self.stateChanged.emit('初始化仪器')
        for key in ['Power1', 'Power2', 'DMM1', 'DMM2', 'DMM3', 'DMM4', 'DMM5']:
            if hasattr(self, key):
                getattr(self, key).reconfig()

    def run_fake(self):
        Vc, Ve = 0, 0
        self.setup_resist()
        self.reconfig()

        while True:
            Vce, Ic = self._test_npn(Vc, Ve)
            if Vce > self.arg.Vce: break
            Vc += 0.5

        while True:
            Vce, Ic = self._test_npn(Vc, Ve)
            if Ic > self.arg.Ic: break
            Ve += 0.05

        pass

    def setup_resist(self, Req):
        # 尝试电阻的等级
        self.R.set_resist1(Req)
        self.R.set_resist2(Req)
        self._R = Req

    def run_npn(self):
        def search_point(target_Vce: float, target_Ic: float):
            self.setup_resist(target_Vce * target_Ic * 0.1)

            # 匹配 (Vce, 0)
            self.stateChanged.emit('第1步: 匹配 (Vce, 0)')
            Vc = target_Vce
            Ve = 0
            while True:
                Vce, Ic = self._test_npn(Vc, Ve)
                match direction(Vce, target_Vce):
                    case -1:
                        print(f'adjust Vce lower', flush=True)
                        Vc += 1
                        continue
                    case 0:
                        print(f'match 1')
                        break
                    case 1:
                        print(f'adjust Vce upper', flush=True)
                        Vc -= 0.1
                        continue

            # 匹配 (Vce, 0) => (Vce, Ic)
            while True:
                Vce, Ic = self._test_npn(Vc, Ve)
                match direction(Ic, target_Ic):
                    case -1:
                        print(f'adjust Ic lower', flush=True)
                        Ve += 0.1
                        continue
                    case 0:
                        while True:
                            exp = math.floor(math.log(abs(Vce - target_Vce), 10))
                            adjust = 10 ** max(-2, exp)

                            match direction(Vce, target_Vce):
                                case -1:
                                    print(f'adjust Vce lower', flush=True)
                                    Vc += adjust
                                case 0:
                                    self.test_point_matched.emit(Vc, Ve, Vce, Ic)
                                    print(f'-- match {(target_Vce, target_Ic)} => {(Vc, Ve, Vce, Ic)}')
                                    return Vc, Ve, Vce, Ic
                                case 1:
                                    print(f'adjust Vce upper', flush=True)
                                    Vc -= adjust
                            Ve += direction(Ic, target_Ic, 0.1) * 0.01
                            Vce, Ic = self._test_npn(Vc, Ve)
                    case 1:
                        print(f'adjust Ic upper', flush=True)
                        Ve -= 0.01
                        continue

        points: list[tuple[float, float]] = []
        
        def log_range(start, stop):
            xstart = math.log10(start)
            xstop = math.log10(stop)
            return [10 ** (xstart + (xstop - xstart) * i / 5) for i in range(6)]

        # 恒定 Vce 段
        Vce = [self.arg.Vce] * 5
        Ic = log_range(0.1e-3, self.arg.Ic_mid)
        points.extend((v, i) for v, i in zip(Vce, Ic))

        # TODO: 增加二次击穿段

        # 恒定功率段
        Vce = log_range(self.arg.Vce, self.arg.Vce_mid)
        Ic = [self.arg.Pmax / v for v in Vce]
        points.extend((v, i) for v, i in zip(Vce, Ic))

        # 恒定 Ic 段
        Vce = log_range(self.arg.Vce_mid, 0.010)
        Ic = [self.arg.Ic] * 5
        points.extend((v, i) for v, i in zip(Vce, Ic))

        # 开始测试
        time.sleep(2.000)
        self.reconfig()
        for Vce, Ic in points:
            search_point(Vce, Ic)

    def run_pnp(self):
        self.begin

    def abort(self):
        with ExitStack() as stack:
            self._mutex.lock()
            stack.callback(self._mutex.unlock)
            self._paused = True
