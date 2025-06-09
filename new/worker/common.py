from __future__ import annotations
import logging, asyncio, math, time, typing
from dataclasses import dataclass
from contextlib import AsyncExitStack, ExitStack
from PySide6.QtCore import QObject, Signal, Slot, QMutex
from ..types import Devices, Measurement
from ..dmm import MultiMeter
from ..power import PowerCV
from ..resist import Resist

_log = logging.getLogger(__name__)

@dataclass
class TargetArgument:
    Vce: float
    Ic: float
    Rc: str
    Re: str

    Vc_max: float
    Ve_max: float
    Vceo: float
    Vebo: float
    Vcbo: float

    output_time: float
    total_time: float

class EventPoint:
    def __init__(self, Vc: float, Ve: float):
        self.Vc = Vc
        self.Ve = Ve
        self.state: typing.Literal['start', 'vc', 've', 'output'] = 'start'

        self.vc = asyncio.Event()
        self.ve_vce = asyncio.Event()
        self.ve_ic = asyncio.Event()
        self.output = asyncio.Event()

        self.start: float = math.nan
        self.ve_start: float = math.nan
        self.ve_vce_stop: float = math.nan
        self.ve_ic_stop: float = math.nan
        self.output_stop: float = math.nan

    @property
    def ve_stop(self) -> float:
        stop = max(self.ve_vce_stop, self.ve_ic_stop)
        if math.isnan(stop):
            assert not math.isnan(stop), 've_stop 未设置'
        return stop

class DeviceWorker:
    def __init__(self, dev: Devices, type: str):
        self.type = type
        self._dev_info = dev
        self._disconnects: AsyncExitStack | None = None

    @property
    def fake(self) -> bool:
        return self._dev_info.fake

    @property
    def powerVc(self):
        return self.Power1 if self.type == 'NPN' else self.Power2

    @property
    def powerVe(self):
        return self.Power2 if self.type == 'NPN' else self.Power1
    
    @property
    def Vce(self):
        return 'DMM1'

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

    async def __aenter__(self):
        _log.info('正在连接仪器...')
        async with AsyncExitStack() as stack:
            fake = self._dev_info.fake

            self._dmms = MultiMeter(fake)
            await self._dmms.connects(self._dev_info.dmms)
            stack.push_async_callback(self._dmms.disconnects)

            self.Power1 = PowerCV(self._dev_info.power1, fake)
            stack.callback(self.Power1.disconnects)

            self.Power2 = PowerCV(self._dev_info.power2, fake)
            stack.callback(self.Power2.disconnects)

            self.R = Resist(self._dev_info.resist, fake)
            stack.callback(self.R.disconnects)

            await self.reconfig()
            stack.enter_context(self.Power1.remote())
            stack.enter_context(self.Power2.remote())

            self._disconnects = stack.pop_all()
        _log.info('仪器连接成功')
        return self

    async def __aexit__(self, *exc):
        if self._disconnects is None: return
        _log.info('正在断开仪器...')
        return await self._disconnects.aclose()
    
    async def reconfig(self):
        _log.info('正在初始化仪器...')
        for power in [self.Power1, self.Power2]: power.reconfig()
        await self._dmms.reconfig()
        self.R.reconfig()
        _log.info('仪器初始化完成')
    
    def set_resist(self, Rc: str, Re: str):
        _log.info(f'{Rc = }, {Re = }')
        match self.type:
            case 'NPN': return self.R.set_resists(Re, Rc)
            case 'PNP': return self.R.set_resists(Rc, Re)
            case t: assert False, f'无效的晶体管类型({t})'

    def set_power_current_limits(self, current: float):
        for power in [self.powerVc, self.powerVe]:
            power.set_limit_current(current)
    
    async def power_control(self, events: EventPoint, common: TargetArgument):
        if not self.fake:
            await asyncio.sleep(4.000) # 每次施加电压前等待样品冷却

        for power in [self.powerVc, self.powerVe]:
            power.set_voltage(0)

        with self.powerVc, self.powerVe:
            events.start = time.monotonic()
            
            _log.info('[power] 开始输出 Vc, 等待 Vce 稳定...')
            self.set_power_current_limits(common.Ic * 5)
            self.powerVc.set_voltage(events.Vc)

            events.state = 'vc'
            await events.vc.wait()

            _log.info('[power] 开始输出 Ve, 等待 Vce 和 Ic 稳定...')
            self.set_power_current_limits(common.Ic * 2.2)
            self.powerVe.set_voltage(events.Ve)
            events.ve_start = time.monotonic()
            events.state = 've'
            await events.ve_vce.wait()
            await events.ve_ic.wait()
            ve_duration = events.ve_stop - events.ve_start
            _log.info(f'[power] 从 Ve 开始输出到 Vce 和 Ic 稳定耗时 {ve_duration:.3f}s')

            _log.info(f'[power] 采集{common.output_time:.3f}秒数据...')
            self.set_power_current_limits(common.Ic * 1.3)
            events.state = 'output'
            await asyncio.sleep(common.output_time)
            events.output.set()
            events.output_stop = time.monotonic()

            _log.info('[power] 停止采集数据, 设置 Vc 为 Ve, 等待 Vc 设置生效...')
            self.powerVc.set_voltage(events.Ve)
            await asyncio.sleep(1.000)

        _log.info('[power] 停止输出')
    
    async def setup_dmm_ranges(self, target: TargetArgument):
        rate = await self._dmms.auto_sample(target.total_time)

        volts = await self._dmms.set_volt_range(**{
            self.Vce: abs(target.Vce),
            self.Vbe: target.Vebo,
            self.Vcb: target.Vcbo,
        })
        currs = await self._dmms.set_curr_range(**{
            self.Ic: target.Ic,
            self.Ie: target.Ic,
        })
        return rate, { **volts, **currs }

    async def acquire(self, limits: dict[str, float]) -> dict[Measurement, list[float]]:
        results: dict[Measurement, asyncio.Task[list[float]]] = {}
        async with asyncio.TaskGroup() as tg:
            meas_keys: list[Measurement] = ['Vce', 'Ic', 'Vbe', 'Vcb', 'Ie']
            for meas in meas_keys:
                dmm: str = getattr(self, meas)
                def parse(data: bytes) -> float:
                    value = float(data)
                    limit = limits.get(dmm, math.inf)
                    if abs(value) > limit:
                        raise Exception(f'[{meas}] 测量值 {value} 超出限制 {limit}, 可能是测量错误')
                    return value
                results[meas] = tg.create_task(self._dmms[dmm].acquire_one(parse))
        return { meas: result.result() for meas, result in results.items() }

class Cancellation(Exception):
    pass

class Context(QObject):
    stateChanged = Signal(bool)
    targetStarted = Signal(float, float) # target Vce, target Ic
    message = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mutex = QMutex()
        self._paused: bool = False
        self._loop = asyncio.new_event_loop()

    @Slot()
    def start(self, type: str, dev: Devices, builder: typing.Callable[[Context], Runner]):
        try:
            self._paused = False

            device = DeviceWorker(dev, type)
            runner = builder(self)

            _log.info(f'开始测试 {type} 型晶体管')
            self.stateChanged.emit(True)

            async def _run(runner: Runner, device: DeviceWorker):
                async with device:
                    return await runner.run(device)

            self._loop.run_until_complete(_run(runner, device))
        except Cancellation:
            _log.warning('测试被终止')
            self.message.emit('测试被终止')
        except Exception:
            _log.exception('测试时发生错误')
            self.message.emit('测试失败，请在运行日志查看错误')
        finally:
            self.stateChanged.emit(False)

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

class Runner(typing.Protocol):
    async def run(self, device: DeviceWorker): ...
