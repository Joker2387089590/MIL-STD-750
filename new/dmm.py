import asyncio, logging, re, time, math
from asyncio import StreamReader, StreamWriter
from collections import Counter
import numpy as np

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

def _func(name: str):
    volts = ('DMM1', 'DMM2', 'DMM3')
    return 'VOLTage' if name in volts else 'CURRent'

async def dwrite(writer: StreamWriter, *cmds: bytes | str):
    for cmd in cmds: 
        if isinstance(cmd, str): cmd = cmd.encode()
        assert isinstance(cmd, bytes)
        cmd = cmd.rstrip() + b'\n'
        writer.write(cmd)
    await writer.drain()

async def xread(reader: StreamReader, timeout: float = 3):
    async with asyncio.timeout(timeout):
        line = await reader.readline()
        return line.rstrip()

async def query(writer: StreamWriter, reader: StreamReader, cmd: bytes | str, timeout: float = 3):
    await dwrite(writer, cmd)
    return await xread(reader, timeout)

def top(values: list[float], step: float):
    assert values
    mid = (max(values) + min(values)) / 2
    xtop, = Counter(v // step for v in values if v > mid).most_common(1)
    stop, tcount = xtop
    top = stop * step
    return top, tcount

class _Meter:
    def __init__(self, name: str, reader: StreamReader, writer: StreamWriter) -> None:
        self.name = name
        self.reader = reader
        self.writer = writer

    @property
    def func(self):
        volts = ('DMM1', 'DMM2', 'DMM3')
        return 'VOLTage' if self.name in volts else 'CURRent'

    async def write(self, *cmds: bytes | str):
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
        values = [200e-3, 2, 20, 200, 1000]
        has_range = False
        for text, value in zip(texts, values):
            if abs(volt) < value * 0.95:
                await self.write(f'SENSe:VOLTage:DC:RANGe {text}')
                has_range = True
                break

        if not has_range:
            raise Exception(f'测试电压 {volt}V 超过万用表最大量程')
        
    async def set_curr_range(self, curr: float):
        texts = ['200uA', '2mA', '20mA', '200mA', '2A', '10A']
        values = [200e-6, 2e-3, 20e-3, 200e-3, 2, 10]

        has_range = False
        for text, value in zip(texts, values):
            if abs(curr) < value * 0.95:
                await self.write(f'SENSe:CURRent:DC:RANGe {text}')
                has_range = True
                break

        if not has_range:
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
        await self.write(b'TRIGger:SOURce EXTernal', b'INIT')
        opc = await self.query(b'*OPC?')
        if opc != b'1':
            _log.warning(f'[{self.name}] reconfig opc: {opc}')

    # async def fetch(self):
    #     try:
    #         # sample count & data points
    #         sample = int(await self.query(b'SAMPLe:COUNt?'))
    #         async with asyncio.timeout(10):
    #             while True:
    #                 points = int(await self.query(b'DATA:POINts?'))
    #                 if points >= sample: break

    #         # fetch
    #         begin = time.monotonic()
    #         response = await self.query(b'FETCh?', timeout=10)
    #         end = time.monotonic()
    #         elapsed = int((end - begin) * 1000)

    #         if not response.endswith(b'\n'):
    #             _log.warning(f'[{self.name}] 不完整的响应')

    #         if response == b'NULL':
    #             raise Exception('仪器未被触发')
            
    #         range = float(await self.query(f'{self.func}:RANGe?'))
            
    #         values = [float(r) for r in response.split(b',')]
    #         values = [v for v in values if v < range]
    #         vcount = len(values)
    #         if vcount == 0:
    #             raise Exception('仪器未被触发')
            
    #         _log.info(f'[{self.name}][{elapsed}ms] fetch {vcount}')
    #         return values
    #     except TimeoutError as e:
    #         await self.write(b'ABORt')
    #         ex = e
    #     except Exception as e:
    #         ex = e
    #     return ex

    async def acquire(self, event: asyncio.Event | None = None):
        test = event.is_set if event else lambda: True
        while test():
            await asyncio.sleep(0.050)
            response = await self.query(b'R?')
            
            if response == b'NULL':
                yield []
                continue

            matches = re.match(_data_points_pattern, response)
            assert matches, 'R? 响应格式错误'

            count = int(matches[1])
            data = matches[2][count + 1:]
            yield [float(d) for d in data.split(b',')]

class MultiMeter:
    def __init__(self):
        self.streams: dict[str, tuple[StreamReader, StreamWriter]] = {}

    def __getitem__(self, name: str):
        return _Meter(name, *self.streams[name])
    
    def _all(self):
        for name, stream in self.streams.items():
            yield _Meter(name, *stream)

    async def connects(self, devices_ip: list[str]):
        async with asyncio.TaskGroup() as tg:
            for i, ip in enumerate(devices_ip):
                tg.create_task(self.connect_one(f'DMM{i + 1}', ip))

    async def connect_one(self, name: str, ip: str):
        try:
            reader, writer = await asyncio.open_connection(ip, 5025, limit=4096 * 1024)
            idn = await query(writer, reader, b'*IDN?')
            _log.debug(f'[{name}] IDN from {ip}: {idn}')
            self.streams[name] = (reader, writer)
        except Exception:
            _log.exception(f'[{name}] 连接失败')
            raise

    async def disconnects(self):
        for meter in self._all(): meter.disconnect()
        self.streams.clear()

    async def reconfig(self):
        async with asyncio.TaskGroup() as tg:
            for meter in self._all():
                tg.create_task(meter.reconfig())

    async def set_volt_range(self, **volts: float):
        for name, volt in volts.items():
            await self[name].set_volt_range(volt)

    async def set_curr_range(self, **currs: float):
        for name, curr in currs.items():
            await self[name].set_curr_range(curr)
    
    async def auto_sample(self, total_duration: float, plc: str = '0.1'):
        rate = plc_to_rate[plc]
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
        async with asyncio.TaskGroup() as tg:
            for meter in self._all():
                tg.create_task(meter.initiate())

    def acquire(self, name: str):
        return self[name].acquire()
