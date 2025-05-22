from __future__ import annotations
import time, math, logging, asyncio
from dataclasses import dataclass
from typing import Callable
from contextlib import ExitStack
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot, QMutex
from ..types import *
from ..resist import Resist, ohm_to_float
from ..dmm import MultiMeter
from ..power import PowerCV

_log = logging.getLogger(__name__)

@dataclass
class Common:
    Vc: float
    Ve: float
    Vce: float
    Ic: float
    Rc: str
    Re: str
    Vceo: float
    Vebo: float
    Vcbo: float
    output_time: float
    total_time: float

def average(values: list[float]):
    s = len(values)
    return 0.0 if s == 0 else sum(values) / s

class Events:
    def __init__(self, common: Common):
        self.common = common

        self.state: Literal['vc', 've', 'output'] = 'vc'
        self.vc = asyncio.Event()
        self.ve_vce = asyncio.Event()
        self.ve_ic = asyncio.Event()
        self.output = asyncio.Event()

        self.start: float = math.nan
        self.ve_start: float = math.nan
        self.ve_stop: float = math.nan
        self.output_stop: float = math.nan

        self.rate: float = math.nan
        self.all_vce: list[float] = []
        self.all_dmm2: list[float] = []
        self.all_dmm3: list[float] = []
        self.all_ic: list[float] = []
        self.all_ie: list[float] = []

    def mapping(self, time: float):
        return int((time - self.start) * self.rate)

    def _output_range(self):
        return self.mapping(self.ve_stop), self.mapping(self.output_stop)

    @property
    def Vce(self):
        b, e = self._output_range()
        return average(self.all_vce[b:e])

    @property
    def dmm2(self):
        b, e = self._output_range()
        return average(self.all_dmm2[b:e])

    @property
    def dmm3(self):
        b, e = self._output_range()
        return average(self.all_dmm3[b:e])

    @property
    def Ic(self):
        b, e = self._output_range()
        return average(self.all_ic[b:e])

    @property
    def Ie(self):
        b, e = self._output_range()
        return average(self.all_ie[b:e])

    def results(self):
        b, e = self.mapping(self.ve_stop), self.mapping(self.output_stop)
        return ReferResult(
            target_Vce = self.common.Vce,
            target_Ic=self.common.Ic,

            Vce = average(self.all_vce[b:e]),
            Ic = average(self.all_ic[b:e]),

            Vc = self.common.Vc,
            Ve = self.common.Ve,
            Rc = self.common.Rc,
            Re = self.common.Re,

            Vc_delay = self.ve_start - self.start,
            Ve_delay = self.ve_stop - self.ve_start,

            all_vce = self.all_vce,
            all_dmm2 = self.all_dmm2,
            all_dmm3 = self.all_dmm3,
            all_ic = self.all_ic,
            all_ie = self.all_ie,
        )

    def exec_result(self):
        b, e = self.mapping(self.ve_stop), self.mapping(self.output_stop)
        return dict(
            all_vce = self.all_vce[b:e],
            all_dmm2 = self.all_dmm2[b:e],
            all_dmm3 = self.all_dmm3[b:e],
            all_ic = self.all_ic[b:e],
            all_ie = self.all_ie[b:e],
        )

    def ve_delay(self):
        return self.ve_stop - self.ve_start

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
    message = Signal(str)
    logged = Signal(str)
    plots = Signal(list, str, str)

    # refer
    referTested = Signal(ReferResult)
    referComplete = Signal(ReferAllResult)

    # exec
    execTested = Signal(ExecResult)
    execComplete = Signal(ExecAllResult)

    Power1: PowerCV
    Power2: PowerCV
    R: Resist
    type: Literal['NPN', 'PNP']

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

    def setup_devices(self, dev: Devices):
        _log.info('正在连接仪器...')
        self._async(self._dmms.connects(dev.dmms))
        self.Power1 = PowerCV(dev.power1)
        self.Power2 = PowerCV(dev.power2)
        self.R = Resist(dev.resist)

    def disconnect_devices(self):
        _log.info('正在断开仪器...')
        if hasattr(self, 'Power1'): self.Power1.disconnects(); del self.Power1
        if hasattr(self, 'Power2'): self.Power2.disconnects(); del self.Power2
        if hasattr(self, 'R'): self.R.disconnects(); del self.R
        self._async(self._dmms.disconnects())

    @property
    def powerVc(self):
        return self.Power1 if self.type == 'NPN' else self.Power2

    @property
    def powerVe(self):
        return self.Power2 if self.type == 'NPN' else self.Power1

    @property
    def Vcb(self):
        return 'DMM3' if self.type == 'NPN' else 'DMM2'

    @property
    def Vbe(self):
        return 'DMM2' if self.type == 'NPN' else 'DMM3'

    @property
    def Ic(self):
        return 'DMM4' if self.type == 'NPN' else 'DMM5'

    @property
    def Ie(self):
        return 'DMM5' if self.type == 'NPN' else 'DMM4'

    @Slot()
    def start(self, arg: ReferArgument | ExecArgument, dev: Devices):
        try:
            with ExitStack() as stack:
                _log.warning(f'正在测试 {arg.name}，极性 {arg.type}')

                self._paused = False
                self.begin = time.time()
                self.type = arg.type

                stack.callback(self.disconnect_devices)
                self.setup_devices(dev)

                _log.info('正在初始化仪器...')
                for power in [self.Power1, self.Power2]: power.reconfig()
                self._async(self._dmms.reconfig())
                self.R.reconfig()

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
            self.message.emit('测试被终止')
        except Exception:
            _log.exception('测试时发生错误')
            self.message.emit('测试失败，请在运行日志查看错误')
        finally:
            self.stateChanged.emit(False)

    async def power_control(self, events: Events):
        # 每次施加电压前等待样品冷却
        time.sleep(4.000)

        common = events.common

        for power in [self.powerVc, self.powerVe]:
            power.set_voltage(0)

        with self.powerVc, self.powerVe:
            events.start = time.monotonic()

            self.powerVc.set_limit_current(common.Ic * 5)
            self.powerVe.set_limit_current(common.Ic * 5)
            self.powerVc.set_voltage(common.Vc)
            
            _log.info('[power] wait Vc...')
            await events.vc.wait() # 等待 Vce 就绪
            _log.info('[power] Vc finish')

            self.powerVc.set_limit_current(common.Ic * 2.2)
            self.powerVe.set_limit_current(common.Ic * 2.2)
            self.powerVe.set_voltage(common.Ve)
            events.ve_start = time.monotonic()
            _log.info('[power] wait Ve...')
            await events.ve_vce.wait() # 等待 Vce 就绪
            await events.ve_ic.wait() # 等待 Ic 就绪
            _log.info('[power] Ve finish')

            # 采集 Vce, Ic 一段时间
            self.powerVc.set_limit_current(common.Ic * 1.3)
            self.powerVe.set_limit_current(common.Ic * 1.3)
            _log.info('[power] wait output...')
            await asyncio.sleep(common.output_time)
            _log.info('[power] output finish')
            events.output.set()

            events.output_stop = time.monotonic()
            self.powerVc.set_voltage(common.Ve)
            _log.info('[power] set Vc to Ve')

    def test_common(self, common: Common):
        self.check_abort()
        events = Events(common)

        def on_vce(events: Events):
            volts = events.all_vce
            
            duration = 0.100
            sample = int(events.rate * duration)
            if sample >= len(volts):
                last = volts[-sample:]
                vce = abs(average(last))
                if vce > common.Vceo:
                    raise Exception(f'Vcb ({vce:.3f}V) 超出 Vcbo ({common.Vceo}V)')

            match events.state:
                case 'vc':
                    duration = 0.200
                    sample = int(events.rate * duration)
                    
                    if len(volts) < sample: return None
                    
                    times = np.linspace(0, duration, sample)
                    last = volts[-sample:]
                    co = np.polyfit(np.array(times), np.array(last), 1)
                    k, b = float(co[0]), float(co[1])

                    hint = abs(events.common.Vc * 0.05 / events.common.output_time)
                    _log.info(f'[refer] vc acquire: Vc = {events.common.Vc}, {hint = }V/s, {k = :.3f}, {b = :.3f}')
                    _vc_hint = events.common.Vc
                    no_bias = abs(b - _vc_hint) < _vc_hint * 0.10 + 1
                    if abs(k) < hint and no_bias:
                        events.vc.set()
                        events.state = 've'
                        return b

                case 've':
                    duration = 0.100
                    sample = int(events.rate * duration)
                    times = np.linspace(0, duration, sample)

                    last = volts[-sample:]
                    co = np.polyfit(np.array(times), np.array(last), 1)
                    k, b = float(co[0]), float(co[1])

                    vce_hint = events.common.Vc - events.common.Ve
                    hint = abs(vce_hint * 0.1 / events.common.output_time)
                    _log.info(f'[refer] ve acquire: Vc = {events.common.Vc}, Ve = {events.common.Ve}, {hint = } {k = :.3f}, {b = :.3f}')
                    if abs(k) < hint:
                        prev = len(volts) - sample
                        events.ve_stop = events.start + prev / events.rate
                        events.ve_vce.set()

        def on_vcb(events: Events):
            volts = events.all_dmm2 if self.Vcb == 'DMM2' else events.all_dmm3
            duration = 0.100
            sample = int(events.rate * duration)
            if len(volts) < sample: return None
            last = volts[-sample:]
            vcb = abs(average(last))
            if vcb > common.Vcbo:
                raise Exception(f'Vcb ({vcb:.3f}V) 超出 Vcbo ({common.Vcbo}V)')

        def on_veb(events: Events):
            volts = events.all_dmm2 if self.Vbe == 'DMM2' else events.all_dmm3
            duration = 0.100
            sample = int(events.rate * duration)
            if len(volts) < sample: return None
            last = volts[-sample:]
            veb = abs(average(last))
            if veb > common.Vebo:
                raise Exception(f'Veb ({veb:.3f}V) 超出 Vebo ({common.Vebo}V)')

        def on_ic(events: Events):
            match events.state:
                case 've':
                    duration = 0.200
                    sample = int(events.rate * duration)
                    times = np.linspace(0, duration, sample)

                    if len(events.all_ic) < sample: return None
                    last = events.all_ic[-sample:]
                    co = np.polyfit(np.array(times), np.array(last), 1)
                    k, b = float(co[0]), float(co[1])

                    hint = events.common.Ic * 0.05 / events.common.output_time
                    _log.info(f'[refer] Ic acquire: {hint = } {k = :.6f}, {b = :.6f}')
                    if abs(k) < abs(hint):
                        events.ve_ic.set()

        async def vce(events: Events):
            async for xvolts in self._dmms['DMM1'].acquire(events.output):
                events.all_vce.extend(xvolts)
                on_vce(events)

        async def vcb(events: Events):
            async for vs in self._dmms[self.Vcb].acquire(events.output):
                events.all_dmm2.extend(vs)
                on_vcb(events)

        async def vbe(events: Events):
            async for vs in self._dmms[self.Vbe].acquire(events.output):
                events.all_dmm3.extend(vs)
                on_veb(events)

        async def ic(events: Events):
            async for xcurr in self._dmms[self.Ic].acquire(events.output):
                events.all_ic.extend(xcurr)
                on_ic(events)

        async def ie(events: Events):
            async for vs in self._dmms[self.Ie].acquire(events.output):
                events.all_ie.extend(vs)

        async def total_timeout(events: Events):
            try:
                async with asyncio.timeout(events.common.total_time):
                    await events.output.wait()
            except TimeoutError as e:
                raise Exception('电路建立稳态的时间过长') from e

        async def _test(events: Events):
            events.rate = await self._dmms.auto_sample(common.total_time)

            await self._dmms.initiate()
            fp = None
            try:
                async with asyncio.TaskGroup() as tg:
                    fp = tg.create_task(self.power_control(events))
                    tg.create_task(vce(events), name='vce')
                    tg.create_task(ic(events), name='ic')
                    tg.create_task(ie(events), name='ie')
                    tg.create_task(vcb(events), name='vcb')
                    tg.create_task(vbe(events), name='vbe')
                    tg.create_task(total_timeout(events), name='total_timeout')

                xr = events.results()
                return xr
            finally:
                if fp is not None: fp.cancel()

        return self._async(_test(events))

    def run_refer(self, arg: ReferArgument):
        all_results = ReferAllResult(arg, [])
        if arg.type == 'NPN':
            for target in arg.targets:
                item = self.search_npn(arg, target)
                all_results.results.append(item)
        else:
            for target in arg.targets:
                item = self.search_pnp(arg, target)
                all_results.results.append(item)
        self.referComplete.emit(all_results)
        self.message.emit('测试成功，请在数据表查看数据，在持续测试界面进一步测试')

    def set_resist(self, Rc: str, Re: str):
        _log.info(f'{Rc = }, {Re = }')
        match self.type:
            case 'NPN': return self.R.set_resists(Re, Rc)
            case 'PNP': return self.R.set_resists(Rc, Re)
            case t: assert False, f'无效的晶体管类型({t})'

    def search_npn(self, arg: ReferArgument, target: ReferTarget):
        target_Vce = target.Vce
        target_Ic = target.Ic

        _log.info(f'[{arg.type}] 测试目标: Vce {target_Vce}, Ic {target_Ic}')

        self.set_resist(target.Rc, target.Re)

        self._async(self._dmms.set_volt_range(
            DMM1=target_Vce,
            DMM2=target_Vce,
            DMM3=target_Vce,
        ))
        self._async(self._dmms.set_curr_range(
            DMM4=target_Ic,
            DMM5=target_Ic,
        ))

        self.counter = 0
        def _test(Vc: float, Ve: float):
            if Vc > arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')
            self.counter += 1
            if self.counter > 50:
                raise Exception('多次调整 Vc/Ve 也未能达到目标条件')

            xresult = self.test_common(Common(
                Vc=Vc,
                Ve=Ve,
                Vce=target.Vce,
                Ic=target.Ic,
                Rc=target.Rc,
                Re=target.Re,
                Vcbo=arg.Vcbo,
                Vceo=arg.Vceo,
                Vebo=arg.Vebo,
                output_time=arg.duration,
                total_time=arg.stable_duration,
            ))
            self.referTested.emit(xresult)
            return xresult
        return self.search(target_Vce, target_Ic, ohm_to_float(target.Rc), _test)

    def search_pnp(self, arg: ReferArgument, target: ReferTarget):
        target_Vce = -target.Vce
        target_Ic = target.Ic

        _log.info(f'[{arg.type}] 测试目标: Vce {target_Vce}, Ic {target_Ic}')

        Req = abs(target.Vce) / target_Ic
        Rc, Re = self.R.set_resists(target.Rc, target.Re)
        _log.info(f'{Req = }, {Rc = }, {Re = }')

        self._async(self._dmms.set_volt_range(
            DMM1=abs(target_Vce),
            DMM2=abs(target_Vce),
            DMM3=abs(target_Vce),
        ))
        self._async(self._dmms.set_curr_range(
            DMM4=target_Ic,
            DMM5=target_Ic,
        ))

        self.counter = 0
        def _test(Vc: float, Ve: float):
            if Vc > arg.Vc_max: raise Exception('Vc 超出限值')
            if Ve > arg.Ve_max: raise Exception('Ve 超出限值')
            if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
            if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')
            self.counter += 1
            if self.counter > 50:
                raise Exception('多次调整 Vc/Ve 也未能达到目标条件')

            xresult = self.test_common(Common(
                Vc=Vc,
                Ve=Ve,
                Vce=target_Vce,
                Ic=target.Ic,
                Rc=target.Rc,
                Re=target.Re,
                Vcbo=arg.Vcbo,
                Vceo=arg.Vceo,
                Vebo=arg.Vebo,
                output_time=arg.duration,
                total_time=arg.stable_duration,
            ))
            self.referTested.emit(xresult)
            return xresult
        return self.search(target_Vce, target_Ic, ohm_to_float(Rc), _test)

    def search(self, target_Vce: float, target_Ic: float, Rc: float, _test: Callable[[float, float], ReferResult]):
        self.targetStarted.emit(target_Vce, target_Ic)

        for power in [self.powerVc, self.powerVe]:
            power.set_limit_current(target_Ic * 1.3)

        xresult: ReferResult | None = None
        try:
            Ve_hint = max(target_Ic * Rc, 1)
            Vc_hint = Ve_hint + target_Vce
            _log.debug(f'{Vc_hint = }, {Ve_hint = }')

            # 匹配 (Vce, 0)
            Vc = Ve = 0
            Vce, Ic = 0, 0
            while True:
                diff = abs(Vce - target_Vce)
                adjust = min(100, diff)
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
            Ve = Ve_hint * 0.6
            Vc = Ve + abs(Vce_hint)
            adjust = Ve_hint * 0.1
            while True:
                xresult = _test(Vc, Ve)
                Vce, Ic = xresult.Vce, xresult.Ic
                _log.info(f'calc hint: {Ve = }, {Ic = }')
                match direction(Vce, target_Vce, 0.1):
                    case -1:
                        Vc += abs(Vce - target_Vce) * 0.8
                    case 0:
                        pass
                    case 1:
                        Vc -= abs(Vce - target_Vce)

                match direction(Ic, target_Ic):
                    case -1:
                        Vc += adjust
                        Ve += adjust
                        _log.debug(f'[search] adjust Ic too low, {Vc = }, {Ve = }')
                        continue
                    case 0:
                        break
                    case 1:
                        Vc -= adjust * 0.1
                        Ve -= adjust * 0.1
                        _log.debug(f'[search] adjust Ic too high {Vc = }, {Ve = }')
                        continue
            _log.debug(f'match Ic: {Ic}')

            while True:
                diff = abs(Vce - target_Vce)
                adjust = max(0.1, diff)
                match direction(Vce, target_Vce):
                    case -1:
                        Vc += adjust
                        _log.debug(f'adjust Vce lower: {Vc = }')
                    case 0:
                        break
                    case 1:
                        Vc -= adjust
                        _log.debug(f'adjust Vce lower: {Vc = }')
                xresult = _test(Vc, Ve)
                Vce, Ic = xresult.Vce, xresult.Ic
            _log.debug(f'match Vce {Vce}, Ic {Ic}')
            return xresult
        finally:
            pass

    def run_exec(self, arg: ExecArgument):
        all_results = ExecAllResult([])
        for item in arg.items:
            result = self._async(self.exec(arg, item))
            all_results.results.append(result)
            self.execTested.emit(result)
        self.execComplete.emit(all_results)

    async def exec(self, arg: ExecArgument, item: ExecItem):
        _log.info(f'[exec] start {arg}, {item}')
        self.check_abort()

        def on_vce(events: Events):
            volts = events.all_vce

            match events.state:
                case 'vc':
                    duration = 0.200
                    sample = int(events.rate * duration)
                    times = np.linspace(0, duration, sample)

                    if len(volts) < sample: return None
                    last = volts[-sample:]
                    co = np.polyfit(np.array(times), np.array(last), 1)
                    k, b = float(co[0]), float(co[1])

                    hint = abs(events.common.Vc * 0.05 / events.common.output_time)
                    _log.info(f'[refer] vc acquire: Vc = {events.common.Vc}, {hint = }V/s, {k = :.3f}, {b = :.3f}')
                    _vc_hint = events.common.Vc
                    no_bias = abs(b - _vc_hint) < _vc_hint * 0.10 + 1
                    if abs(k) < hint and no_bias:
                        events.vc.set()
                        events.state = 've'
                        return b

        async def delay(events: Events, delay: float):
            await events.vc.wait()
            _log.info('[exec] wait ve delay...')
            events.ve_start = time.monotonic()
            await asyncio.sleep(delay)
            events.ve_stop = time.monotonic()
            _log.info('[exec] ve delay finish')
            events.ve_vce.set()
            events.ve_ic.set()

        async def vce(events: Events):
            empty_count = 0
            async for xvolts in self._dmms['DMM1'].acquire(events.output):
                if len(xvolts) == 0:
                    empty_count += 1
                else:
                    empty_count = 0
                if empty_count >= 3: return
                events.all_vce.extend(xvolts)
                on_vce(events)

        async def dmm2(events: Events):
            empty_count = 0
            async for vs in self._dmms['DMM2'].acquire(events.output):
                if len(vs) == 0:
                    empty_count += 1
                else:
                    empty_count = 0
                if empty_count >= 3: return
                events.all_dmm2.extend(vs)

        async def dmm3(events: Events):
            async for vs in self._dmms['DMM3'].acquire(events.output):
                events.all_dmm3.extend(vs)

        async def ic(events: Events):
            async for xcurr in self._dmms[self.Ic].acquire(events.output):
                events.all_ic.extend(xcurr)

        async def ie(events: Events):
            async for vs in self._dmms[self.Ie].acquire(events.output):
                events.all_ie.extend(vs)

        async def total_timeout(events: Events):
            try:
                async with asyncio.timeout(events.common.total_time):
                    await events.output.wait()
            except TimeoutError as e:
                raise Exception('电路建立稳态的时间过长') from e

        events = Events(Common(
            Vc=item.Vc,
            Ve=item.Ve,
            Vce=item.Vce,
            Ic=item.Ic,
            Rc=item.Rc,
            Re=item.Re,
            Vcbo=arg.Vcbo,
            Vceo=arg.Vceo,
            Vebo=arg.Vebo,
            output_time=item.duration,
            total_time=10
        ))
        events.rate = await self._dmms.auto_sample(events.common.total_time)
        await self._dmms.set_volt_range(
            DMM1=item.refer_Vce,
            DMM2=item.refer_Vce,
            DMM3=item.refer_Vce,
        )
        await self._dmms.set_curr_range(
            DMM4=item.refer_Ic,
            DMM5=item.refer_Ic,
        )

        if arg.type == 'NPN':
            self.R.set_resists(item.Rc, item.Re)
        else:
            self.R.set_resists(item.Re, item.Rc)

        await self._dmms.initiate()
        fp = None
        try:
            async with asyncio.TaskGroup() as tg:
                fp = tg.create_task(self.power_control(events))
                tg.create_task(vce(events), name='vce')
                tg.create_task(ic(events), name='ic')
                tg.create_task(ie(events), name='ie')
                tg.create_task(dmm2(events), name='dmm2')
                tg.create_task(dmm3(events), name='dmm3')
                tg.create_task(total_timeout(events), name='total_timeout')
                tg.create_task(delay(events, item.Ve_delay))
            return ExecResult(
                type=arg.type,
                item=item,
                rate=events.rate,
                ve_start=events.ve_start - events.start,
                ve_stop=events.ve_stop - events.start,
                output_stop=events.output_stop - events.start,
                all_vce=events.all_vce,
                all_dmm2=events.all_dmm2,
                all_dmm3=events.all_dmm3,
                all_ic=events.all_ic,
                all_ie=events.all_ie,
            )
        finally:
            if fp is not None: fp.cancel()

class ReferWorker(Worker):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
