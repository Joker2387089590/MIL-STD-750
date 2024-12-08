from __future__ import annotations
import time, math, logging
import numpy
from typing import Callable
from contextlib import ExitStack
from PySide6.QtCore import QObject, Signal, Slot, QMutex
from .types import ReferData, Argument
from .resist import Resist, ohm_to_float
from .dmm import Meter
from .power import PowerCV

log = logging.getLogger(__name__)

class Cancellation(Exception):
    pass

def direction(value, target, range = 0.05):
    if value * target <= 0: return -1
    if abs(value) < abs(target) * (1 - range):
        return -1
    elif abs(value) > abs(target) * (1 + range):
        return 1
    else:
        return 0
    
class _Handler(logging.Handler):
    def __init__(self, worker: Worker):
        super().__init__(logging.INFO)
        self.worker = worker
        self.setFormatter(logging.Formatter(
            fmt='[{asctime}.{msecs:03.0f}][{levelname}] {message}',
            datefmt='%H:%M:%S',
            style='{'
        ))

    def emit(self, record):
        msg = self.format(record)

        if record.levelno >= logging.FATAL:
            fore, back = 'rgb(255, 255, 255)', 'rgb(190, 0, 0)'
        elif record.levelno >= logging.ERROR:
            fore, back = 'rgb(240, 0, 0)', 'rgb(255, 255, 255)'
        elif record.levelno >= logging.WARNING:
            fore, back = 'rgb(225, 125, 50)', 'rgb(255, 255, 255)'
        elif record.levelno >= logging.INFO:
            fore, back = 'rgb(0, 125, 60)', 'rgb(255, 255, 255)'
        else:
            fore, back = 'rgb(54, 96, 146)', 'rgb(255, 255, 255)'
        
        html = f'<pre style="color: {fore}; background-color: {back}">{msg}</pre>'
        self.worker.logged.emit(html)

class Worker(QObject):
    stateChanged = Signal(bool)
    targetStarted = Signal(float, float) # target Vce, target Ic
    pointTested = Signal(float, float) # Vce, Ic
    matched = Signal(ReferData)
    logged = Signal(str)
    
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
        log.addHandler(_Handler(self))

    def check_abort(self):
        with ExitStack() as stack:
            self._mutex.lock()
            stack.callback(self._mutex.unlock)
            if self._paused: raise Cancellation()

    def abort(self):
        with ExitStack() as stack:
            self._mutex.lock()
            stack.callback(self._mutex.unlock)
            self._paused = True

    def test_common(self, V1: float, V2: float):
        self.check_abort()
        self.Power1.set_voltage(V1)
        self.Power2.set_voltage(V2)

        begin = time.time()
        with self.Power1, self.Power2:
            time.sleep(0.075)
            for dmm in [self.DMM1, self.DMM2, self.DMM3, self.DMM4, self.DMM5]:
                dmm.initiate()
            time.sleep(0.300)
        end = time.time()
        log.debug(f'[common] output {end - begin:.3f}s')

        # 等待万用表计算，以及等待管子冷却
        time.sleep(0.600)

        results = dict(
            DMM1=self.DMM1.fetch(),
            DMM2=self.DMM2.fetch(),
            DMM3=self.DMM3.fetch(),
            DMM4=self.DMM4.fetch(),
            DMM5=self.DMM5.fetch(),
            Power1=V1,
            Power2=V2,
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

    def disconnect_devices(self):
        if hasattr(self, 'DMM1'): self.DMM1.disconnects(); del self.DMM1
        if hasattr(self, 'DMM2'): self.DMM2.disconnects(); del self.DMM2
        if hasattr(self, 'DMM3'): self.DMM3.disconnects(); del self.DMM3
        if hasattr(self, 'DMM4'): self.DMM4.disconnects(); del self.DMM4
        if hasattr(self, 'DMM5'): self.DMM5.disconnects(); del self.DMM5
        if hasattr(self, 'Power1'): self.Power1.disconnects(); del self.Power1
        if hasattr(self, 'Power2'): self.Power2.disconnects(); del self.Power2
        if hasattr(self, 'R'): self.R.disconnects(); del self.R

    @Slot()
    def start(self, arg: Argument, dev: dict):
        try:
            self.run(arg, dev)
        except Cancellation:
            log.warning('终止测试')
        except Exception:
            log.exception('运行出现错误')
        finally:
            self.stateChanged.emit(False)

    def run(self, arg: Argument, dev: dict):
        with ExitStack() as stack:
            self._paused = False
            self.arg = arg
            self.begin = time.time()

            self.setup_devices(dev)
            stack.callback(self.disconnect_devices)

            self.stateChanged.emit(True)
            stack.enter_context(self.Power1.remote())
            stack.enter_context(self.Power2.remote())

            if arg.type == 'NPN':
                for target_Vce, target_Ic in self.arg.targets:
                    self.search_npn(target_Vce, target_Ic)
            else:
                for target_Vce, target_Ic in self.arg.targets:
                    self.search_pnp(-target_Vce, target_Ic)

    def search_npn(self, target_Vce: float, target_Ic: float):
        Req = target_Vce / target_Ic
        Re, Rc = self.R.set_resists(Req, Req)
        log.info(f'{Req = }, {Rc = }, {Re = }')

        for vdmm in [self.DMM1, self.DMM2, self.DMM3]:
            vdmm.set_volt_range(target_Vce)
        for idmm in [self.DMM4, self.DMM5]:
            idmm.set_curr_range(target_Ic)

        def _test(Vc: float, Ve: float):
            if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')

            results = self.test_common(Vc, Ve)
            xresult = ReferData(
                target_Vce=target_Vce,
                target_Ic=target_Ic,
                Vce=results['DMM1'],
                Ic=results['DMM4'],
                Vc=Vc,
                Ve=Ve,
                Rc=Rc,
                Re = Re,
            )
            self.pointTested.emit(xresult.Vce, xresult.Ic)
            return xresult
        
        self.search(target_Vce, target_Ic, ohm_to_float(Rc), _test)

    def search_pnp(self, target_Vce: float, target_Ic: float):
        Req = abs(target_Vce / target_Ic)
        Re, Rc = self.R.set_resists(Req, Req)
        log.info(f'{Req = }, {Rc = }, {Re = }')

        def _test(Vc: float, Ve: float):
            if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > self.arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')
            results = self.test_common(Ve, Vc)
            xresult = ReferData(
                target_Vce=target_Vce,
                target_Ic=target_Ic,
                Vce=-results['DMM1'],
                Ic=results['DMM4'],
                Vc=Vc,
                Ve=Ve,
                Rc=Rc,
                Re = Re,
            )
            self.pointTested.emit(-xresult.Vce, xresult.Ic)
        self.search(target_Vce, target_Ic, ohm_to_float(Rc), _test)
    
    def search(self, target_Vce: float, target_Ic: float, Rc: float, _xtest: Callable[[float, float], ReferData]):
        _count = object()
        _count.x = 0
        def _test(Vc, Ve):
            if _count.x > 40: raise Exception('测试时间过长')
            _count.x += 1
            return _xtest(Vc, Ve)

        Ve_hint = target_Ic * Rc
        Vc_hint = Ve_hint + target_Vce
        log.debug(f'{Vc_hint = }, {Ve_hint = }')

        # 匹配 (Vce, 0)
        Vc = Ve = 0
        Vce, Ic = 0, 0
        while True:
            diff = abs(Vce - target_Vce)
            adjust = min(20, diff)
            match direction(Vce, target_Vce):
                case -1:
                    log.debug(f'adjust Vce lower')
                    Vc += adjust
                case _:
                    break
            xresult = _test(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            if Ic > target_Ic:
                raise Exception('Ic 过大，样片可能已故障')
        while True:
            diff = abs(Vce - target_Vce)
            adjust = min(6, diff)
            match direction(Vce, target_Vce):
                case -1:
                    Vc -= adjust
                    log.debug(f'adjust Vce lower: {Vc = }')
                case _:
                    break
            xresult = _test(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            if Ic > target_Ic:
                raise Exception('Ic 过大，样片可能已故障')
        while True:
            diff = abs(Vce - target_Vce)
            adjust = min(1, diff)
            match direction(Vce, target_Vce):
                case -1:
                    Vc += adjust
                    log.debug(f'adjust Vce lower: {Vc = }')
                case _:
                    break
            xresult = _test(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            if Ic > target_Ic:
                raise Exception('Ic 过大，样片可能已故障')

        log.debug(f'match Vce: {Vce}')
        Vce_hint = Vce

        # 匹配 (Vce, 0) => (Vce, Ic)
        Ves = []
        Ics = []
        adjust = Ve_hint / 10
        for i in range(1, 5):
            Ve += adjust
            xresult = _test(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            Ves.append(Ve)
            Ics.append(Ic)
            log.debug(f'calc hint: {Ve = }, {Ic = }')

            match direction(Ic, target_Ic):
                case -1:
                    continue
                case 0:
                    break
                case 1:
                    break
        
        co = numpy.polyfit(numpy.array(Ics), numpy.array(Ves), 1)
        
        Ve = co[0] * target_Ic + co[1]
        Vc = Ve + Vce_hint
        log.debug(f'test hint: {Vc = }, {Ve = }')

        while True:
            xresult = _test(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            Ves.append(Ve)
            Ics.append(Ic)
            co = numpy.polyfit(numpy.array(Ics), numpy.array(Ves), 1)
            if direction(Ic, target_Ic) == 0: break
            Ve -= co[0] * (Ic - target_Ic)

        while True:
            d = direction(Vce, target_Vce)
            if d == 0: break
            Vc -= direction(Vce, target_Vce) * abs(Vce - target_Vce)
            log.debug(f'adjust Vce {Vc = }')
