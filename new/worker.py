from __future__ import annotations
import time, math, logging, asyncio
import numpy
from typing import Callable
from contextlib import ExitStack
from PySide6.QtCore import QObject, Signal, Slot, QMutex
from .types import *
from .resist import Resist, ohm_to_float
from .dmm import Meter, MultiMeter
from .power import PowerCV

_log = logging.getLogger(__name__)

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

class Worker(QObject):
    stateChanged = Signal(bool)
    targetStarted = Signal(float, float) # target Vce, target Ic
    pointTested = Signal(float, float) # Vce, Ic
    matched = Signal(ReferResult)
    logged = Signal(str)
    
    Power1: PowerCV
    Power2: PowerCV
    R: Resist

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mutex = QMutex()
        self._paused = False
        self._loop = asyncio.new_event_loop()
        self._dmms = MultiMeter()

    def _async(self, coro):
        return self._loop.run_until_complete(coro)

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

    def test_common(self, V1: float, V2: float, output_time: float):
        self.check_abort()
        async def _test():
            self.Power1.set_voltage(V1)
            self.Power2.set_voltage(V2)

            await self._dmms.initiate()

            # TODO: ARB
            begin = time.monotonic()
            with self.Power1, self.Power2:
                time.sleep(output_time)
            end = time.monotonic()
            _log.debug(f'[common] output {end - begin:.3f}s')

            results = await self._dmms.fetch()
            return { name: result[0] for name, result in results.items() }

        return self._async(_test())
    
    def setup_devices(self, dev: Devices):
        _log.info('正在连接仪器...')
        self._async(self._dmms.connects(dev.dmms))
        self.Power1 = PowerCV(dev.power1)
        self.Power2 = PowerCV(dev.power2)
        self.R = Resist(dev.resist)

        _log.info('正在初始化仪器...')
        for power in [self.Power1, self.Power2]:
            power.reconfig()
        self._async(self._dmms.reconfig())
        self.R.reconfig()

    def disconnect_devices(self):
        _log.info('正在断开仪器...')
        if hasattr(self, 'Power1'): self.Power1.disconnects(); del self.Power1
        if hasattr(self, 'Power2'): self.Power2.disconnects(); del self.Power2
        if hasattr(self, 'R'): self.R.disconnects(); del self.R
        self._async(self._dmms.disconnects())

    @Slot()
    def start(self, arg: ReferArgument | ExecArgument, dev: Devices):
        try:
            with ExitStack() as stack:
                self._paused = False
                self.begin = time.time()

                self.setup_devices(dev)
                stack.callback(self.disconnect_devices)

                self.stateChanged.emit(True)
                stack.enter_context(self.Power1.remote())
                stack.enter_context(self.Power2.remote())

                if isinstance(arg, ReferArgument):
                    self.run_refer(arg)
                elif isinstance(arg, ExecArgument):
                    self.run_exec(arg)
                else:
                    raise Exception(f'参数错误: {arg}')
        except Cancellation:
            _log.warning('测试被终止')
        except Exception:
            _log.exception('测试时发生错误')
        finally:
            self.stateChanged.emit(False)

    def run_refer(self, arg: ReferArgument):
        if arg.type == 'NPN':
            for target_Vce, target_Ic in arg.targets:
                self.search_npn(arg, target_Vce, target_Ic)
        else:
            for target_Vce, target_Ic in arg.targets:
                self.search_pnp(arg, -target_Vce, target_Ic)

    def search_npn(self, arg: ReferArgument, target_Vce: float, target_Ic: float):
        Req = target_Vce / target_Ic
        Re, Rc = self.R.set_resists(Req, Req)
        _log.info(f'{Req = }, {Rc = }, {Re = }')

        for vdmm in [self.DMM1, self.DMM2, self.DMM3]:
            vdmm.set_volt_range(target_Vce)
        for idmm in [self.DMM4, self.DMM5]:
            idmm.set_curr_range(target_Ic)

        def _test(Vc: float, Ve: float):
            if Vc > arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')

            results = self.test_common(Vc, Ve)
            xresult = ReferResult(
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

    def search_pnp(self, arg: ReferArgument, target_Vce: float, target_Ic: float):
        Req = abs(target_Vce / target_Ic)
        Re, Rc = self.R.set_resists(Req, Req)
        _log.info(f'{Req = }, {Rc = }, {Re = }')

        def _test(Vc: float, Ve: float):
            if Vc > arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')
            results = self.test_common(Ve, Vc)
            xresult = ReferResult(
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
    
    def search(self, target_Vce: float, target_Ic: float, Rc: float, _xtest: Callable[[float, float], ReferResult]):
        _count = object()
        _count.x = 0
        def _test(Vc, Ve):
            if _count.x > 40: raise Exception('测试时间过长')
            _count.x += 1
            return _xtest(Vc, Ve)

        Ve_hint = target_Ic * Rc
        Vc_hint = Ve_hint + target_Vce
        _log.debug(f'{Vc_hint = }, {Ve_hint = }')

        # 匹配 (Vce, 0)
        Vc = Ve = 0
        Vce, Ic = 0, 0
        while True:
            diff = abs(Vce - target_Vce)
            adjust = min(20, diff)
            match direction(Vce, target_Vce):
                case -1:
                    _log.debug(f'adjust Vce lower')
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
                    _log.debug(f'adjust Vce lower: {Vc = }')
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
                    _log.debug(f'adjust Vce lower: {Vc = }')
                case _:
                    break
            xresult = _test(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            if Ic > target_Ic:
                raise Exception('Ic 过大，样片可能已故障')

        _log.debug(f'match Vce: {Vce}')
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
            _log.debug(f'calc hint: {Ve = }, {Ic = }')

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
        _log.debug(f'test hint: {Vc = }, {Ve = }')

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
            _log.debug(f'adjust Vce {Vc = }')

    def run_exec(self, arg: ExecArgument):
        ...