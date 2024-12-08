import pyvisa, time, re, logging
from typing import Literal
from pyvisa.resources.tcpip import TCPIPInstrument
from pyvisa.constants import ResourceAttribute, VI_ERROR_TMO
from pyvisa.errors import VisaIOError

log = logging.getLogger(__name__)

class Meter:
    def __init__(self, ip: str, func: Literal['VOLTage', 'CURRent']):
        self.ip = ip
        try:
            rm = pyvisa.ResourceManager()
            self.instr: TCPIPInstrument = rm.open_resource(f'TCPIP::{ip}::INSTR')
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
            if abs(volt) < r * 0.95:
                self.instr.write(f'SENSe:VOLTage:DC:RANGe {t}')
                return
        raise Exception('测试电压超过万用表最大量程')

    def set_curr_range(self, curr: float):
        ranges: list[float] = [200e-6, 2e-3, 20e-3, 200e-3, 2, 10]
        texts = ['200uA', '2mA', '20mA', '200mA', '2A', '10A']
        for r, t in zip(ranges, texts):
            if abs(curr) < r * 0.95:
                self.instr.write(f'SENSe:CURRent:DC:RANGe {t}')
                return
        raise Exception('测试电流超过万用表最大量程')

    def initiate(self):
        self.instr.write(f'INIT;*OPC?')
    
    data_points_pattern = re.compile(r'#(\d)(.*)')

    def read_by_R(self):
        end = time.time() + 3
        while time.time() < end:
            points = int(self.instr.query('DATA:POINts?'))
            if points <= 0:
                time.sleep(0.100)
                continue

            result = self.instr.query('R?')
            matches = re.match(Meter.data_points_pattern, result)
            assert matches
            count = int(matches[1])
            data = matches[2][count + 1:]
            datas = data.split(',')
            return float(datas[-1])
        raise Exception('万用表测量触发失败')

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

import asyncio
from asyncio import StreamReader, StreamWriter
from collections import Counter

def func(name: str):
    volts = ('DMM1', 'DMM2', 'DMM3')
    return 'VOLTage' if name in volts else 'CURRent'

def xwrite(writer: StreamWriter, cmd: bytes | str):
    if isinstance(cmd, str):
        cmd = cmd.encode()
    writer.write(cmd + b'\n')

async def dwrite(writer: StreamWriter, *cmds: bytes | str):
    for cmd in cmds: xwrite(writer, cmd)
    await writer.drain()

async def xread(reader: StreamReader, timeout: float = 3):
    async with asyncio.timeout(timeout):
        line = await reader.readline()
        return line.rstrip()

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
            await dwrite(writer, b'*IDN?')
            idn = await xread(reader)
            log.debug(f'[{name}] IDN from {ip}: {idn}')
            self.streams[name] = (reader, writer)
        except Exception:
            log.exception(f'[{name}] 连接失败')

    async def disconnects(self):
        for name, stream in self.streams.items():
            reader, writer = stream
            writer.close()

    async def reconfig(self):
        async with asyncio.TaskGroup() as tg:
            for name, stream in self.streams.items():
                reader, writer = stream
                async def reconfig_one():
                    # RST
                    await dwrite(writer, b'*RST')
                    await asyncio.sleep(1.500)

                    # config
                    await dwrite(writer,
                        b'TRIGger:COUNt 1',
                        b'SAMPle:COUNt 10000',
                        f'FUNC "{func(name)}"',
                        b'*OPC?'
                    )

                    # OPC
                    opc = await xread(reader)
                    if opc != '1':
                        log.warning(f'[{name}] reconfig opc is not 1')
            
                tg.create_task(reconfig_one())

    async def set_sampling_duration(self, duration: float):
        max_points = 10000
        plc_to_rate = {
            '0.001': 50000.0,
            '0.01': 5000.0,
            '0.1': 500.0,
            '1': 50.0,
            '10': 5.0,
            '100': 0.5,
        }
        for plc, rate in plc_to_rate.items():
            if rate * duration <= max_points:
                break

        async with asyncio.TaskGroup() as tg:
            for name, stream in self.streams.items():
                reader, writer = stream
                tg.create_task(dwrite(writer, f'{func(name)}:NPLC {plc}'))

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
                async def init():
                    await dwrite(writer,
                        b'TRIGger:SOURce EXTernal',
                        b'INIT',
                        b'*OPC?'
                    )
                    opc = await xread(reader)
                    if opc != '1':
                        log.warning(f'[{name}] initiate opc is not 1')
                tg.create_task(init())

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
            await dwrite(writer, b'FETCh?')
            begin = time.monotonic()
            response = await xread(reader, 10)
            end = time.monotonic()

            elapsed = (end - begin) * 1000

            if response == b'NULL':
                raise Exception('仪器未被触发')
            
            values = [float(r) for r in response.split(',')]
            vcount = len(values)
            if vcount == 0:
                raise Exception('仪器未被触发')
            
            mid = (max(values) + min(values)) / 2
            xtop, = Counter(v // 0.001 for v in values if v > mid).most_common(1)
            top, tcount = xtop

            log.info(f'[{name}][{elapsed}ms] fetch {vcount}, top {top}, top count {tcount}')
            return name, (top, values)
        except TimeoutError as e:
            await dwrite(writer, b'ABORt')
            ex = e
        except Exception as e:
            ex = e
        return name, ex
