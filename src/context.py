import traceback, time, math, logging
from typing import Literal
from dataclasses import dataclass, asdict
from contextlib import ExitStack
from PySide6.QtCore import QObject, Signal, Slot, QMutex
from .resist import Resist
from .dmm import Meter
from .power import PowerCV

log = logging.getLogger('运行')

@dataclass
class Argument:
    type: Literal['NPN', 'PNP']
    Vce: float
    Ic: float
    Pmax: float
    hFE: float
    Vc_max: float
    Ve_max: float

    # targets: list[tuple[float, float]] = [] # Vce, Ic

    @property
    def Ic_mid(self): return self.Pmax / self.Vce

    @property
    def Vce_mid(self): return self.Pmax / self.Ic

@dataclass
class Play:
    V1: float
    V2: float
    R1: float
    R2: float
    duration: float

@dataclass
class NpnResult:
    Vc:  float = math.nan
    Ve:  float = math.nan
    Vce: float = math.nan
    Vbe: float = math.nan
    Vcb: float = math.nan
    Ic:  float = math.nan
    Ie:  float = math.nan
    Rc:  str = ''
    Re:  str = ''

@dataclass
class PnpResult:
    Vc:  float = math.nan
    Ve:  float = math.nan
    Vce: float = math.nan
    Vbc: float = math.nan
    Veb: float = math.nan
    Ic:  float = math.nan
    Ie:  float = math.nan
    Rc:  str = ''
    Re:  str = ''

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

    def check_abort(self):
        with ExitStack() as stack:
            self._mutex.lock()
            stack.callback(self._mutex.unlock)
            if self._paused: raise Exception('终止测试')

    def abort(self):
        with ExitStack() as stack:
            self._mutex.lock()
            stack.callback(self._mutex.unlock)
            self._paused = True

    def _test_no_cache(self, V1: float, V2: float, output_time: float = 0.100):
        self.check_abort()

        self.Power1.set_voltage(V1)
        self.Power2.set_voltage(V2)

        with self.Power1, self.Power2:
            # NOTE: 此处开始打开电源
            time.sleep(0.150)
            for dmm in [self.DMM1, self.DMM2, self.DMM3, self.DMM4, self.DMM5]:
                dmm.initiate()
            time.sleep(0.850)

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
    
    def setup_devices(self, dev: dict):
        log.info('连接仪器')
        self.DMM1 = Meter(dev['DMM1'], 'VOLTage')
        self.DMM2 = Meter(dev['DMM2'], 'VOLTage')
        self.DMM3 = Meter(dev['DMM3'], 'VOLTage')
        self.DMM4 = Meter(dev['DMM4'], 'CURRent')
        self.DMM5 = Meter(dev['DMM5'], 'CURRent')
        self.Power1 = PowerCV(dev['Power1'])
        self.Power2 = PowerCV(dev['Power2'])
        self.R = Resist(dev['R'])
        time.sleep(2.000)

        log.info('初始化仪器')
        for key in ['Power1', 'Power2', 'DMM1', 'DMM2', 'DMM3', 'DMM4', 'DMM5']:
            if hasattr(self, key):
                getattr(self, key).reconfig()

    @Slot()
    def run(self, arg: Argument, dev: dict):
        try:
            self._paused = False
            self.arg = arg
            self.begin = time.time()

            self.setup_devices(dev)

            self.stateChanged.emit('is_running')
            if arg.type == 'NPN':
                self.run_npn() 
            else:
                self.run_pnp()
            self.stateChanged.emit('pass')
        except Exception as e:
            log.exception('运行出现错误')
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

    def setup_resist(self, Req):
        self._R = Req
        self.R.set_resists(Req)

    def run_npn(self):
        caches: dict[tuple[float, float, str, str], tuple[float, float]] = {}

        def _test(Vc: float, Ve: float, Re: str, Rc: str):
            if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')

            key = (Vc, Ve, Re, Rc)
            if key in caches: return caches[key]

            results = self._test_no_cache(Vc, Ve)
            xresult = NpnResult(
                Vc=results['Power1'],
                Ve=results['Power2'],
                Vce=results['DMM1'],
                Vbe=results['DMM2'],
                Vcb=results['DMM3'],
                Ic=results['DMM4'],
                Ie=results['DMM5'],
                Rc=Rc,
                Re=Re,
            )
            log.debug(f'[test:{time.time() - self.begin:.3f}s] {as_str(xresult)}')
            self.npn_tested.emit(xresult)

            cache = (xresult.Vce, xresult.Ic)
            caches[key] = cache
            return cache
        
        def search_point(target_Vce: float, target_Ic: float):
            Req = target_Vce / target_Ic * 0.1
            Re, Rc = self.R.set_resists(Req, Req)

            # 匹配 (Vce, 0)
            Vc = target_Vce * 0.7
            Ve = 0
            while True:
                Vce, Ic = _test(Vc, Ve, Rc, Re)
                match direction(Vce, target_Vce):
                    case -1:
                        log.debug(f'adjust Vce lower')
                        Vc += 1
                        continue
                    case 0:
                        log.debug(f'match 1')
                        break
                    case 1:
                        log.debug(f'adjust Vce upper')
                        Vc -= 0.1
                        continue

            # 匹配 (Vce, 0) => (Vce, Ic)
            while True:
                Vce, Ic = _test(Vc, Ve, Rc, Re)
                match direction(Ic, target_Ic):
                    case -1:
                        log.debug(f'adjust Ic lower')
                        Ve += 0.1
                        continue
                    case 0:
                        while True:
                            exp = math.floor(math.log(abs(Vce - target_Vce), 10))
                            adjust = 10 ** max(-2, exp)

                            match direction(Vce, target_Vce):
                                case -1:
                                    Vc += adjust
                                    log.debug(f'adjust Vce lower {Vc}')
                                case 0:
                                    log.debug(f'-- match {(target_Vce, target_Ic)} => {(Vc, Ve, Vce, Ic)}')
                                    return Vc, Ve, Vce, Ic
                                case 1:
                                    Vc -= adjust
                                    log.debug(f'adjust Vce upper {Vc}')
                            Ve += direction(Ic, target_Ic, 0.1) * 0.01
                            Vce, Ic = _test(Vc, Ve, Rc, Re)
                    case 1:
                        log.debug(f'adjust Ic upper')
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
        Vce = log_range(self.arg.Vce_mid, 0.200)
        Ic = [self.arg.Ic] * 5
        points.extend((v, i) for v, i in zip(Vce, Ic))

        # 开始测试
        for Vce, Ic in points:
            Vc, Ve, Vce, Ic = search_point(Vce, Ic)
            self.test_point_matched.emit(Vc, Ve, Vce, Ic)

    def run_pnp(self):
        caches: dict[tuple[float, float, str, str], tuple[float, float]] = {}
    
        def _test(Vc: float, Ve: float, Rc: str, Re: str):
            if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')
            results = self._test_no_cache(Ve, Vc)
            xresult = PnpResult(
                Vc=results['Power2'],
                Ve=results['Power1'],
                Vce=-results['DMM1'],
                Vbc=-results['DMM2'],
                Veb=-results['DMM3'],
                Ic=results['DMM5'],
                Ie=results['DMM4'],
                Rc=Rc,
                Re=Re,
            )
            print(f'[test:{time.time() - self.begin:.3f}s] {as_str(xresult)}')
            self.pnp_tested.emit(xresult)
            return xresult.Vce, xresult.Ic
        
        def search_point(target_Vce: float, target_Ic: float):
            Req = target_Vce / target_Ic * 0.1
            Rc, Re = self.R.set_resists(Req, Req)

            # 匹配 (Vce, 0)
            Vc = target_Vce * 0.7
            Ve = 0
            while True:
                Vce, Ic = _test(Vc, Ve, Rc, Re)
                match direction(Vce, target_Vce):
                    case -1:
                        log.debug(f'adjust Vce lower')
                        Vc += 1
                        continue
                    case 0:
                        log.debug(f'match 1')
                        break
                    case 1:
                        log.debug(f'adjust Vce upper')
                        Vc -= 0.1
                        continue

            # 匹配 (Vce, 0) => (Vce, Ic)
            while True:
                Vce, Ic = _test(Vc, Ve)
                match direction(Ic, target_Ic):
                    case -1:
                        log.debug(f'adjust Ic lower')
                        Ve += 0.1
                        continue
                    case 0:
                        while True:
                            exp = math.floor(math.log10(abs(Vce - target_Vce)))
                            adjust = 10 ** max(-2, exp)

                            match direction(Vce, target_Vce):
                                case -1:
                                    Vc += adjust
                                    log.debug(f'adjust Vce lower {Vc}')
                                case 0:
                                    log.debug(f'-- match {(target_Vce, target_Ic)} => {(Vc, Ve, Vce, Ic)}')
                                    return Vc, Ve, Vce, Ic
                                case 1:
                                    Vc -= adjust
                                    log.debug(f'adjust Vce upper {Vc}')
                            Ve += direction(Ic, target_Ic, 0.1) * 0.01
                            Vce, Ic = _test(Vc, Ve)
                    case 1:
                        log.debug(f'adjust Ic upper')
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
        Vce = log_range(self.arg.Vce_mid, 0.200)
        Ic = [self.arg.Ic] * 5
        points.extend((v, i) for v, i in zip(Vce, Ic))

        for target_Vce, target_Ic in points:
            Vc, Ve, Vce, Ic = search_point(target_Vce, target_Ic)
            self.test_point_matched.emit(Vc, Ve, Vce, Ic)

    def play(self, arg: Play, dev: dict):
        self.setup_devices(dev)
        self.R.set_resists(arg.R1, arg.R2)
        self.Power1.set_voltage(arg.V1)
        self.Power2.set_voltage(arg.V2)
        with self.Power1, self.Power2:
            end = time.time() + arg.duration
            while time.time() < end:
                for dmm in [self.DMM1, self.DMM2, self.DMM3, self.DMM4, self.DMM5]:
                    dmm.initiate()
                results = dict(
                    DMM1=self.DMM1.fetch(),
                    DMM2=self.DMM2.fetch(),
                    DMM3=self.DMM3.fetch(),
                    DMM4=self.DMM4.fetch(),
                    DMM5=self.DMM5.fetch(),
                    Power1=arg.V1,
                    Power2=arg.V2,
                    R=self._R,
                )

    
