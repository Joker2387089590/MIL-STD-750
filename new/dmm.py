import pyvisa
from pyvisa.resources.tcpip import TCPIPInstrument
from pyvisa.constants import ResourceAttribute, VI_ERROR_TMO
from pyvisa.errors import VisaIOError


import asyncio, logging, re, time, math
from asyncio import StreamReader, StreamWriter
from collections import Counter
from typing import Literal
import numpy as np

log = logging.getLogger(__name__)

plc_to_rate = {
    '0.001': 50000.0,
    '0.01': 5000.0,
    '0.1': 500.0,
    '1': 50.0,
    '10': 5.0,
    '100': 0.5,
}

data_points_pattern = re.compile(rb'#(\d)(.*)')
    
def sample_duration(point: int, plc: str):
    rate = plc_to_rate[plc]
    return point / rate

def func(name: str):
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

def parse_R(response: bytes):
    if response == b'NULL': return []
    matches = re.match(data_points_pattern, response)
    assert matches, 'R? 响应格式错误'
    count = int(matches[1])
    data = matches[2][count + 1:]
    return [float(d) for d in data.split(b',')]

import matplotlib.pyplot as plt
import numpy as np

fig_V, ax_V = None, None
fig_I, ax_I = None, None

def _init_plot():
    global fig_V, fig_I, ax_V, ax_I
    if fig_V is not None: return
    fig_V, ax_V = plt.subplots()
    fig_I, ax_I = plt.subplots()

def plot(volts, name, type):
    global fig_V, fig_I, ax_V, ax_I
    _init_plot()
    if type == 'V':
        fig, ax = fig_V, ax_V
    else:
        fig, ax = plt.subplots()

    log.info(f'[plot] {name} {len(volts)}')
    d = sample_duration(len(volts), "0.1")
    times = np.linspace(0, d, len(volts))
    ax.plot(times, volts, '.-')

    ax.set_title(name)
    fig.show()

class MultiMeter:
    def __init__(self):
        self.streams: dict[str, tuple[StreamReader, StreamWriter]] = {}

    async def connects(self, devices_ip: list[str]):
        async with asyncio.TaskGroup() as tg:
            for i, ip in enumerate(devices_ip):
                tg.create_task(self.connect_one(f'DMM{i + 1}', ip))

    async def connect_one(self, name: str, ip: str):
        try:
            reader, writer = await asyncio.open_connection(ip, 5025, limit=4096 * 1024)
            idn = await query(writer, reader, b'*IDN?')
            log.debug(f'[{name}] IDN from {ip}: {idn}')
            self.streams[name] = (reader, writer)
        except Exception:
            log.exception(f'[{name}] 连接失败')
            raise

    async def disconnects(self):
        for name, stream in self.streams.items():
            reader, writer = stream
            writer.write_eof()
            writer.close()
        self.streams.clear()

    async def reconfig(self):
        async with asyncio.TaskGroup() as tg:
            for name, stream in self.streams.items():
                reader, writer = stream
                async def reconfig_one(
                        name: str,
                        reader: StreamReader,
                        writer: StreamWriter):
                    # RST
                    await dwrite(writer, b'*RST')
                    await asyncio.sleep(1.500)

                    # config
                    await dwrite(writer,
                        b'TRIGger:COUNt 1',
                        f'FUNC "{func(name)}"',
                    )

                    # OPC
                    opc = await query(writer, reader, b'*OPC?')
                    if opc != b'1':
                        log.warning(f'[{name}] reconfig opc: {opc}')
            
                tg.create_task(reconfig_one(name, reader, writer))

    # async def set_sampling_duration(self, duration: float):
    #     max_points = 10000
    #     for plc, rate in plc_to_rate.items():
    #         if rate * duration <= max_points:
    #             break

    #     for name, stream in self.streams.items():
    #         reader, writer = stream
    #         sample = duration * rate
    #         await dwrite(writer, f'{func(name)}:NPLC {plc}')
    #         await dwrite(writer, f'SAMPle:COUNt {sample}')
    #         log.debug(f'[{name}] {sample = }, {plc = }')

    async def set_volt_range(self, **volts: float):
        texts = ['200mV', '2V', '20V', '200V', '1000V']
        values = [200e-3, 2, 20, 200, 1000]
        for name, volt in volts.items():
            reader, writer = self.streams[name]
            has_range = False
            for text, value in zip(texts, values):
                if abs(volt) < value * 0.95:
                    await dwrite(writer, f'SENSe:VOLTage:DC:RANGe {text}')
                    has_range = True
                    break
            if not has_range:
                raise Exception('测试电压超过万用表最大量程')

    async def set_curr_range(self, **currs: float):
        texts = ['200uA', '2mA', '20mA', '200mA', '2A', '10A']
        values = [200e-6, 2e-3, 20e-3, 200e-3, 2, 10]
        for name, curr in currs.items():
            reader, writer = self.streams[name]
            has_range = False
            for text, value in zip(texts, values):
                if abs(curr) < value * 0.95:
                    await dwrite(writer, f'SENSe:CURRent:DC:RANGe {text}')
                    has_range = True
                    break
            if not has_range:
                raise Exception('测试电流超过万用表最大量程')
    
    async def initiate(self):
        async with asyncio.TaskGroup() as tg:
            for name, stream in self.streams.items():
                reader, writer = stream
                async def init(
                        name: str,
                        reader: StreamReader,
                        writer: StreamWriter):
                    await dwrite(writer,
                        b'TRIGger:SOURce EXTernal',
                        b'INIT',
                    )

                    opc = await query(writer, reader, b'*OPC?')
                    if opc != b'1':
                        log.warning(f'[{name}] initiate opc: {opc}')
                tg.create_task(init(name, reader, writer))

    async def fetch(self):
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self.fetch_one(name, *stream))
                for name, stream in self.streams.items()
            ]
        
        values: dict[str, tuple[float, list[float]]] = {}
        for task in tasks:
            name, xvalue = task.result()
            if isinstance(xvalue, Exception):
                log.exception(f'[{name}] 采集数据失败', exc_info=xvalue)
                continue
            values[name] = xvalue
        return values
        
    async def fetch_one(self, name: str, reader: StreamReader, writer: StreamWriter):
        try:
            sample = int(await query(writer, reader, b'SAMPLe:COUNt?'))
            # log.debug(f'[{name}] sample {sample}')

            async with asyncio.timeout(10):
                while True:
                    points = int(await query(writer, reader, b'DATA:POINts?'))
                    # log.debug(f'[{name}] points {points}')
                    if points >= sample: break

            begin = time.monotonic()
            response = await query(writer, reader, b'FETCh?', timeout=10)
            end = time.monotonic()
            elapsed = int((end - begin) * 1000)

            if not response.endswith(b'\n'):
                log.warning(f'[{name}] 不完整的响应')

            if response == b'NULL':
                raise Exception('仪器未被触发')
            
            range = float(await query(writer, reader, f'{func(name)}:RANGe?'))
            
            values = [float(r) for r in response.split(b',')]
            values = [v for v in values if v < range]
            vcount = len(values)
            if vcount == 0:
                raise Exception('仪器未被触发')
            
            mid = (max(values) + min(values)) / 2
            step = range / 200
            xtop, = Counter(v // step for v in values if v > mid).most_common(1)
            top, tcount = xtop
            top = top * step

            log.info(f'[{name}][{elapsed}ms] fetch {vcount}, top {top}, top count {tcount}')
            return name, (top, values)
        except TimeoutError as e:
            await dwrite(writer, b'ABORt')
            ex = e
        except Exception as e:
            ex = e
        return name, ex
    
    async def config_sample(self, name: str, plc: str, duration: float = 0.200):
        reader, writer = self.streams[name]
        sample = int(plc_to_rate[plc] * duration)
        times = np.linspace(0, duration, sample)
        await dwrite(writer, 
            f'{func(name)}:NPLC 1',
            f'SAMPle:COUNt {sample}'
        )
        return sample, times
    
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
        for name, stream in self.streams.items():
            reader, writer = stream
            await dwrite(writer, 
                f'{func(name)}:NPLC {plc}',
                *cmds
            )
        return rate

    async def acquire(self, name: str):
        reader, writer = self.streams[name]
        while True:
            response = await query(writer, reader, b'R?')
            yield parse_R(response)
            await asyncio.sleep(0.050)
            
class Meter:
    def __init__(self, ip: str, func: Literal['VOLTage', 'CURRent']):
        self.ip = ip
        try:
            rm = pyvisa.ResourceManager()
            instr = rm.open_resource(f'TCPIP::{ip}::INSTR')
            assert isinstance(instr, TCPIPInstrument)
            self.instr = instr
        except Exception as e:
            raise Exception(f'万用表 {ip} 连接失败') from e
        self.instr.set_visa_attribute(ResourceAttribute.timeout_value, 10_000)
        self.instr.set_visa_attribute(ResourceAttribute.read_buffer_size, 4096 * 1024)
        self.func = func
        self.instr.write('*RST')

    def disconnects(self):
        try:
            self.instr.close()
        except:
            log.exception(f'万用表关闭 {self.ip} 失败')

    def reconfig(self):
        cmds = [
            'TRIGger:SOURce EXTernal',
            'TRIGger:COUNt 1',
            'SAMPle:COUNt 10000',
            f'FUNC "{self.func}"',
        ]
        for cmd in cmds:
            self.instr.write(cmd)
            time.sleep(0.100)
    
    def set_sample_duration(self, duration: float):
        plc_to_rate = {
            '0.001': 50000.0,
            '0.01': 5000.0,
            '0.1': 500.0,
            '1': 50.0,
            '10': 5.0,
            '100': 0.5,
        }

        max_points = 10000
        for plc, rate in plc_to_rate.items():
            if rate * duration <= max_points:
                for cmd in [
                    f'VOLTage:NPLC {plc}',
                    f'CURRent:NPLC {plc}',
                ]:
                    self.instr.write(cmd)
                return

    def set_volt_range(self, volt: float):
        texts = ['200e-3', '2', '20', '200', '1000']
        for t in texts:
            r = float(t)
            if abs(volt) < r * 0.85:
                self.instr.write(f'SENSe:VOLTage:DC:RANGe {t}')
                return
        raise Exception('测试电压超过万用表最大量程')

    def set_curr_range(self, curr: float):
        ranges: list[float] = [200e-6, 2e-3, 20e-3, 200e-3, 2, 10]
        texts = ['200uA', '2mA', '20mA', '200mA', '2A', '10A']
        for r, t in zip(ranges, texts):
            if abs(curr) < r * 0.85:
                self.instr.write(f'SENSe:CURRent:DC:RANGe {t}')
                return
        raise Exception('测试电流超过万用表最大量程')

    def initiate(self):
        self.instr.write(f'INIT;*OPC?')
    

    # def read_by_R(self):
    #     end = time.time() + 3
    #     while time.time() < end:
    #         points = int(self.instr.query('DATA:POINts?'))
    #         if points <= 0:
    #             time.sleep(0.100)
    #             continue

    #         result = self.instr.query('R?')
    #         matches = re.match(data_points_pattern, result)
    #         assert matches
    #         count = int(matches[1])
    #         data = matches[2][count + 1:]
    #         datas = data.split(',')
    #         return float(datas[-1])
    #     raise Exception('万用表测量触发失败')

def fetch_all(dmms: list[Meter]):
    for dmm in dmms: dmm.instr.write('FETCh?')
    for dmm in dmms:
        try:
            dmm.instr.read()
        except VisaIOError as e:
            if e.error_code == VI_ERROR_TMO:
                dmm.instr.write('ABORt')
            else:
                raise e









