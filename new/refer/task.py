import logging, asyncio, random
import numpy as np
import matplotlib.pyplot as plt
from PySide6.QtCore import QObject, Signal
from ..types import ReferArgument, ReferTarget, ReferTargetResult, ReferResults, Measurement
from ..worker.common import TargetArgument, EventPoint, DeviceWorker, Context
from ..resist import ohm_to_float

_log = logging.getLogger(__name__)

class ReferRunner(QObject):
    referTested = Signal(ReferTargetResult)
    referComplete = Signal(ReferResults)

    def __init__(self, arg: ReferArgument, context: Context):
        super().__init__(context)
        self.context = context
        self.arg = arg
    
    async def run(self, device: DeviceWorker):
        self.device = device
        all_results = ReferResults(self.arg, [])
        for target in self.arg.targets:
            result = await self.run_target(target)
            all_results.results.append(result)
        self.referComplete.emit(all_results)
        self.context.message.emit('测试成功，请在数据表查看数据，在持续测试界面进一步测试')
    
    async def run_target(self, target: ReferTarget) -> ReferTargetResult:
        target_arg = TargetArgument(
            Vce=target.Vce if self.arg.type == 'NPN' else -target.Vce,
            Ic=target.Ic,
            Rc=target.Rc,
            Re=target.Re,
            Vc_max=self.arg.Vc_max,
            Ve_max=self.arg.Ve_max,
            Vceo=self.arg.Vceo,
            Vebo=self.arg.Vebo,
            Vcbo=self.arg.Vcbo,
            output_time=self.arg.duration,
            total_time=self.arg.stable_duration,
        )
        self.context.targetStarted.emit(target.Vce, target.Ic)
        searcher = Search(targ=target_arg, runner=self)
        return await searcher.run()

def direction(value, target, range = 0.05):
    if value * target <= 0: return -1
    if abs(value) < abs(target) * (1 - range):
        return -1
    elif abs(value) > abs(target) * (1 + range):
        return 1
    else:
        return 0

class Search:
    def __init__(self, targ: TargetArgument, runner: ReferRunner):
        self.runner = runner
        self.targ = targ
        self.Rc = ohm_to_float(targ.Rc)

        self.counter = 0

        self.Ve_hint = max(targ.Ic * self.Rc, 1)
        self.Vc_hint = self.Ve_hint + targ.Vce
        _log.debug(f'[search] {self.Vc_hint = }, {self.Ve_hint = }')

    @property
    def device(self):
        return self.runner.device

    async def run(self):
        self.device.set_resist(self.targ.Rc, self.targ.Re)

        rate, limits = await self.device.setup_dmm_ranges(self.targ)
        assert rate > 0, '无法设置万用表采样率'
        self._rate = rate
        self._limits = limits

        dV = await self.search_vce_0(0., 0., 0., 0.)
        return await self.search_vce_ic(dV, self.Ve_hint * 0.6)

    async def search_vce_0(self, Vc: float, Ve: float, Vce: float, Ic: float):
        target = self.targ

        # 100V 步进匹配 (Vce, 0)
        while True:
            match direction(Vce, target.Vce):
                case -1:
                    diff = abs(Vce - target.Vce)
                    (oldVc, Vc) = (Vc, Vc + min(100, diff))
                    _log.debug(f'[search] Vc({oldVc:.2f}V) 过小, Vce偏离目标 {diff:.2f}V')
                case _:
                    break
            xresult = await self.try_with(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            if not self.device.fake and Ic > self.targ.Ic: raise Exception('Ic 过大，样片可能已故障')

        # 6V 步进匹配 (Vce, 0)
        while True:
            match direction(Vce, target.Vce):
                case 1:
                    diff = abs(Vce - target.Vce)
                    (oldVc, Vc) = (Vc, Vc - min(6, diff))
                    _log.debug(f'[search] Vc({oldVc:.2f}V) 过大, Vce偏离目标 {diff:.2f}V')
                case _:
                    break
            xresult = await self.try_with(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            if not self.device.fake and  Ic > target.Ic: raise Exception('Ic 过大，样片可能已故障')

        # 1V 步进匹配 (Vce, 0)
        while True:
            match direction(Vce, target.Vce):
                case -1:
                    diff = abs(Vce - target.Vce)
                    (oldVc, Vc) = (Vc, Vc + min(1, diff))
                    _log.debug(f'[search] Vc({oldVc:.2f}V) 过小, Vce偏离目标 {diff:.2f}V')
                case _:
                    break
            xresult = await self.try_with(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            if not self.device.fake and  Ic > self.targ.Ic: raise Exception('Ic 过大，样片可能已故障')

        Vce_hint = abs(Vce)
        _log.info(f'[search] {Vc = :.2f}, {Vce_hint = :.2f}, {Vce = :.2f}, {Ic = :.2f}')
        return Vce_hint
    
    async def search_vce_ic(self, dV: float, Ve: float):
        target = self.targ
        adjust = self.Ve_hint * 0.1
        while True:
            xresult = await self.try_with(dV + Ve, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic
            vdiff = Vce - target.Vce
            idiff = Ic - target.Ic
            _log.debug(f'[search] {Ve = }, {Ic = }')

            match direction(Vce, target.Vce, 0.1):
                case -1:
                    dV += abs(vdiff) * 0.8
                    _log.debug(f'[search] Vce偏离目标 {vdiff:.2f}V')
                case 0:
                    pass
                case 1:
                    dV -= abs(vdiff)
                    _log.debug(f'[search] Vce偏离目标 {vdiff:.2f}V')

            match direction(Ic, target.Ic):
                case -1:
                    Ve += adjust
                    _log.debug(f'[search] Ic偏离目标 {idiff:.2f}A')
                case 0:
                    break
                case 1:
                    Ve -= adjust * 0.1
                    _log.debug(f'[search] Ic偏离目标 {idiff:.2f}A')
        
        _log.info(f'[search] {dV = :.2f}, {Ve = :.2f}, {Vce = :.2f}, {Ic = :.2f}')

        Vc = dV + Ve
        while True:
            vdiff = Vce - target.Vce
            adjust = max(0.1, abs(vdiff))
            match direction(Vce, target.Vce):
                case -1:
                    Vc += adjust
                    _log.debug(f'[search] Vce偏离目标 {vdiff:.2f}V')
                case 0:
                    break
                case 1:
                    Vc -= adjust
                    _log.debug(f'[search] Vce偏离目标 {vdiff:.2f}V')
            xresult = await self.try_with(Vc, Ve)
            Vce, Ic = xresult.Vce, xresult.Ic

        _log.info(f'[search] 匹配完成: Vc={Vc:.2f}, Ve={Ve:.2f}, Vce={Vce:.2f}, Ic={Ic:.2f}')
        return xresult

    async def try_with(self, Vc: float, Ve: float):
        _log.debug(f'尝试 Vc={Vc}, Ve={Ve}')
        self.runner.context.check_abort()
        if Vc > self.targ.Vc_max: raise Exception('Vc 超出限值')
        if Ve > self.targ.Ve_max: raise Exception('Ve 超出限值')
        if Vc < 0: raise Exception('Vc 匹配失败，请重新测试')
        if Ve < 0: raise Exception('Ve 匹配失败，请重新测试')
        self.counter += 1
        if self.counter > 50:
            raise Exception('多次调整 Vc/Ve 也未能达到目标条件')
        
        events = EventPoint(Vc=Vc, Ve=Ve)
        results: dict[Measurement, list[float]] = { 'Vce': [], 'Ic': [], 'Ie': [], 'Vbe': [], 'Vcb': [] }
        fp = None

        await self.device._dmms.initiate()
        try:
            async with asyncio.TaskGroup() as tg:
                fp = tg.create_task(self.device.power_control(events, self.targ))
                tg.create_task(self.acquire_all(results, events), name='acquire_all')
                tg.create_task(self.total_timeout(events), name='total_timeout')

            b, e = self.mapping(events.ve_stop, events), self.mapping(events.output_stop, events)
            assert b < e, f'采集数据范围错误: {b} >= {e}'

            xresults = ReferTargetResult(
                target_Vce=self.targ.Vce,
                target_Ic=self.targ.Ic,

                Vce=float(np.average(results['Vce'][b:e])),
                Ic=float(np.average(results['Ic'][b:e])),

                Vc = events.Vc,
                Ve = events.Ve,
                Rc = self.targ.Rc,
                Re = self.targ.Re,
                
                Vc_delay = events.ve_start - events.start,
                Ve_delay = events.ve_stop - events.ve_start,

                measurements=results
            )

            self.runner.referTested.emit(xresults)
            return xresults
        finally:
            if fp is not None: fp.cancel()
    
    async def total_timeout(self, events: EventPoint):
        try:
            async with asyncio.timeout(self.targ.total_time):
                await events.output.wait()
        except TimeoutError as e:
            raise Exception('电路建立稳态的时间过长') from e
        
    async def acquire_all(self, results: dict[Measurement, list[float]], events: EventPoint):
        while True:
            if not self.device.fake:
                measurements = await self.device.acquire(self._limits)
                self.runner.context.check_abort()
                for meas, values in measurements.items():
                    results[meas].extend(values)
            else:
                await asyncio.sleep(0.100)  # 模拟采样间隔
                samplecount = int(self._rate * 0.099)
                self.runner.context.check_abort()

                if events.state == 'start':
                    for meas, values in results.items():
                        values.clear()
                else:
                    for meas, values in results.items():
                        if meas == 'Ic' or meas == 'Ie':
                            expect = events.Ve / self.Rc
                            values.extend(random.gauss(expect, expect * 0.05) for _ in range(samplecount))
                        else:
                            expect = events.Vc - events.Ve
                            expect = expect if self.runner.arg.type == 'NPN' else -expect
                            expects = [random.gauss(expect, abs(expect * 0.001)) for _ in range(samplecount)]
                            # expects.sort()
                            values.extend(expects)

            if events.output.is_set(): return

            self.check_vce(results['Vce'], events)
            self.check_ic(results['Ic'], events)
            self.check_vcb(results['Vcb'])
            self.check_veb(results['Vbe'])
    
    def sample_of_last(self, values: list[float], duration: float):
        sample = int(self._rate * duration)
        if len(values) < sample: return None
        return values[-sample:]
    
    def check_vce(self, values: list[float], events: EventPoint):
        # 采样最新的 100ms 数据, 检查是否满足 Vceo
        duration = 0.100
        last = self.sample_of_last(values, duration)
        if not self.device.fake and last is not None:
            vce = np.average(last)
            if abs(vce) > self.targ.Vceo:
                raise Exception(f'Vce {vce} 超出 Vceo 限值 {self.targ.Vceo}')

        match events.state:
            case 'vc':
                # 采样最新的 200ms 数据
                duration = 0.200
                last = self.sample_of_last(values, duration)
                if last is None: return

                # 线性拟合采样数据
                times = np.linspace(0, duration, len(last))
                co = np.polyfit(np.array(times), np.array(last), 1)
                k, b = float(co[0]), float(co[1])

                # 检查斜率 k 是否在允许范围内, 此处假设变化率不超过 5%
                tolerance = 0.05 * abs(events.Vc / self.targ.output_time)
                if abs(k) > tolerance:
                    _log.debug(f'[Vce] Vc 输出尚未稳定: 斜率 {k} 大于 {tolerance}')
                    return

                # 检查 Vce 偏差是否在允许范围内
                bias = abs(abs(np.average(last)) - events.Vc)
                range = events.Vc * 0.10 + 1.0 # 10% 的偏差范围加上 1V 的容错
                if bias > range:
                    _log.debug(f'[Vce] Vc 输出尚未稳定: 偏差 {bias} 大于阈值 {range}')
                    return
                
                _log.info(f'[Vce] Vc 输出进入稳定状态, 斜率 {k}, 偏差 {bias}')
                events.vc.set()

            case 've':
                if events.ve_vce.is_set():
                    return
                
                if last is None: 
                    _log.debug('[Vce] 尚未采集到足够的数据')
                    return
                
                # 线性拟合采样数据
                times = np.linspace(0, duration, len(last))
                co = np.polyfit(np.array(times), np.array(last), 1)
                k, b = float(co[0]), float(co[1])

                # 检查斜率 k 是否在允许范围内, 此处假设变化率不超过 10%
                tolerance = 0.10 * abs(self.targ.Vce / self.targ.output_time)
                if not self.device.fake and abs(k) > tolerance:
                    _log.debug(f'[Vce] Ve 输出尚未稳定: 斜率 {k} 大于 {tolerance}')
                    return
                
                bias = abs(np.average(last) - events.Vc)
                _log.info(f'[Vce] Ve 输出进入稳定状态, 斜率 {k}, 偏差 {bias}')

                # 用测试点数计算 Ve 停止采集的时间，排除最后 100ms
                prev = len(values) - len(last)
                events.ve_vce_stop = events.start + prev / self._rate
                events.ve_vce.set()
            
    def check_ic(self, values: list[float], events: EventPoint):
        match events.state:
            case 've':
                if events.ve_ic.is_set():
                    return
                
                # 采样最新的 200ms 数据
                duration = 0.200
                last = self.sample_of_last(values, duration)
                if last is None: 
                    _log.debug('[Ic] 尚未采集到足够的数据')
                    return
                
                # 线性拟合采样数据
                times = np.linspace(0, duration, len(last))
                co = np.polyfit(np.array(times), np.array(last), 1)
                k, b = float(co[0]), float(co[1])

                # 检查斜率 k 是否在允许范围内, 此处假设变化率不超过 5%
                tolerance = 0.05 * abs(self.targ.Ic / self.targ.output_time)
                if not self.device.fake and abs(k) > tolerance:
                    _log.debug(f'[Ic] 尚未稳定: 斜率 {k} 大于 {tolerance}')
                    return
                
                bias = abs(np.average(last) - self.targ.Ic)
                _log.info(f'[Ic] 进入稳定状态, 斜率 {k}, 偏差 {bias}')
                
                # 用测试点数计算 Ve 停止采集的时间，排除最后 100ms
                prev = len(values) - len(last)
                events.ve_ic_stop = events.start + prev / self._rate
                events.ve_ic.set()

    def check_vcb(self, values: list[float]):
        if self.device.fake: return
        if last := self.sample_of_last(values, 0.100):
            avg = np.average(last)
            if abs(avg) > self.targ.Vcbo:
                raise Exception(f'Vcb {avg} 超出 Vcbo 限值 {self.targ.Vcbo}')
            
    def check_veb(self, values: list[float]):
        if self.device.fake: return
        if last := self.sample_of_last(values, 0.100):
            avg = np.average(last)
            if abs(avg) > self.targ.Vebo:
                raise Exception(f'Veb {avg} 超出 Vebo 限值 {self.targ.Vebo}')
    
    def mapping(self, time: float, events: EventPoint):
        return int((time - events.start) * self._rate)
