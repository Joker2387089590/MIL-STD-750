import asyncio, logging, re, math, typing
from asyncio import StreamReader, StreamWriter
from collections import Counter

_log = logging.getLogger(__name__)

plc_to_rate = {
    '0.001': 50000.0,
    '0.01': 5000.0,
    '0.1': 500.0,
    '1': 50.0,
    '10': 5.0,
    '100': 0.5,
}

_data_points_pattern = re.compile(rb'#(\d)(.*)')

def top(values: list[float], step: float):
    assert values
    mid = (max(values) + min(values)) / 2
    xtop, = Counter(v // step for v in values if v > mid).most_common(1)
    stop, tcount = xtop
    top = stop * step
    return top, tcount

class _Meter:
    def __init__(self, name: str, reader: StreamReader, writer: StreamWriter, fake: bool) -> None:
        self.name = name
        self.reader = reader
        self.writer = writer
        self._fake = fake

    @property
    def func(self):
        volts = ('DMM1', 'DMM2', 'DMM3')
        return 'VOLTage' if self.name in volts else 'CURRent'

    async def write(self, *cmds: bytes | str):
        if self._fake: return
        for cmd in cmds: 
            if isinstance(cmd, str): cmd = cmd.encode()
            assert isinstance(cmd, bytes)
            cmd = cmd.rstrip() + b'\n'
            self.writer.write(cmd)
        await self.writer.drain()

    async def read(self, timeout: float = 3):
        async with asyncio.timeout(timeout):
            line = await self.reader.readline()
            return line.rstrip()
        
    async def query(self, cmd: bytes | str, timeout: float = 3):
        await self.write(cmd)
        return await self.read(timeout)
    
    def disconnect(self):
        self.writer.write_eof()
        self.writer.close()

    async def reconfig(self):
        if self._fake: return

        # RST
        await self.write(b'*RST')
        await asyncio.sleep(1.500)

        # config
        await self.write(b'TRIGger:COUNt 1', f'FUNC "{self.func}"')

        # OPC
        opc = await self.query(b'*OPC?')
        if opc != b'1':
            _log.warning(f'[{self.name}] reconfig opc: {opc}')

    async def set_volt_range(self, volt: float):
        texts = ['200mV', '2V', '20V', '200V', '1000V']
        values = [200e-3, 2., 20., 200., 1000.]
        for text, value in zip(texts, values):
            if abs(volt) < value * 0.90:
                await self.write(f'SENSe:VOLTage:DC:RANGe {text}')
                _log.debug(f'[{self.name}] 设置电压量程: {text}')
                return value
        raise Exception(f'测试电压 {volt}V 超过万用表最大量程')
        
    async def set_curr_range(self, curr: float):
        texts = ['200uA', '2mA', '20mA', '200mA', '2A', '10A']
        values = [200e-6, 2e-3, 20e-3, 200e-3, 2., 10.]
        for text, value in zip(texts, values):
            if abs(curr) < value * 0.90:
                await self.write(f'SENSe:CURRent:DC:RANGe {text}')
                _log.debug(f'[{self.name}] 设置电流量程: {text}')
                return value
        raise Exception('测试电流超过万用表最大量程')
        
    # async def config_sample(self, plc: str, duration: float = 0.200):
    #     sample = int(plc_to_rate[plc] * duration)
    #     times = np.linspace(0, duration, sample)
    #     await self.write(
    #         f'{self.func}:NPLC 1',
    #         f'SAMPle:COUNt {sample}',
    #     )
    #     return sample, times
        
    async def initiate(self):
        if self._fake: return
        await self.write(b'TRIGger:SOURce EXTernal', b'INIT')
        opc = await self.query(b'*OPC?')
        if opc != b'1':
            _log.warning(f'[{self.name}] reconfig opc: {opc}')

    async def acquire(self, event: asyncio.Event | None = None):
        while True:
            if event and event.is_set(): break

            await asyncio.sleep(0.050)
            response = await self.query(b'R?')
            if event and event.is_set(): break
            
            if response == b'NULL':
                yield []
                continue

            matches = re.match(_data_points_pattern, response)
            assert matches, 'R? 响应格式错误'

            count = int(matches[1])
            data = matches[2][count + 1:]

            results = [float(d) for d in data.split(b',')]
            yield results

    async def acquire_one(self, parser: typing.Callable[[bytes], float]) -> list[float]:
        response = await self.query(b'R?')
        if response == b'NULL': return []

        matches = re.match(_data_points_pattern, response)
        assert matches, 'R? 响应格式错误'

        count = int(matches[1])
        data: bytes = matches[2][count + 1:]

        return [parser(d) for d in data.split(b',')]

class MultiMeter:
    def __init__(self, fake: bool = False):
        self._fake = fake
        self.streams: dict[str, tuple[StreamReader, StreamWriter]] = {}

    def __getitem__(self, name: str):
        return _Meter(name, *self.streams[name], self._fake)
    
    def _all(self):
        for name, stream in self.streams.items():
            yield _Meter(name, *stream, self._fake)

    async def connects(self, devices_ip: list[str]):
        async with asyncio.TaskGroup() as tg:
            for i, ip in enumerate(devices_ip):
                tg.create_task(self.connect_one(f'DMM{i + 1}', ip))

    async def connect_one(self, name: str, ip: str):
        try:
            if self._fake:
                meter = _Meter(name, None, None, self._fake) # type: ignore
                self.streams[name] = (None, None) # type: ignore
            else:
                reader, writer = await asyncio.open_connection(ip, 5025, limit=4096 * 1024)
                meter = _Meter(name, reader, writer, self._fake)
                idn = await meter.query(b'*IDN?')
                _log.debug(f'[{name}] IDN from {ip}: {idn}')
                self.streams[name] = (reader, writer)
        except Exception:
            _log.exception(f'[{name}] 连接失败')
            raise

    async def disconnects(self):
        if not self._fake:
            for meter in self._all(): 
                meter.disconnect()
        self.streams.clear()

    async def reconfig(self):
        async with asyncio.TaskGroup() as tg:
            for meter in self._all():
                tg.create_task(meter.reconfig())

    async def set_volt_range(self, **volts: float):
        actual_values: dict[str, float] = {}
        for name, volt in volts.items():
            actual_values[name] = await self[name].set_volt_range(volt)
        return actual_values
    
    async def set_curr_range(self, **currs: float):
        actual_values: dict[str, float] = {}
        for name, curr in currs.items():
            actual_values[name] = await self[name].set_curr_range(curr)
        return actual_values

    async def auto_sample(self, total_duration: float, plc: str = '0.1'):
        rate = plc_to_rate[plc]
        if not self._fake:
            total_sample = int(rate * total_duration)
            if total_sample <= 10000:
                cmds = [f'SAMPle:COUNt {total_sample}']
            else:
                sample = int(rate * 0.200)
                trigger = math.ceil(float(total_sample) / sample)
                cmds = [
                    f'SAMPle:COUNt {sample}',
                    f'TRIGger:COUNt {trigger}'
                ]
            for meter in self._all():
                await meter.write(f'{meter.func}:NPLC {plc}', *cmds)
        return rate
    
    async def initiate(self):
        if self._fake: return
        async with asyncio.TaskGroup() as tg:
            for meter in self._all():
                tg.create_task(meter.initiate())

    def acquire(self, name: str):
        return self[name].acquire()
