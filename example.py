import asyncio, time
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
from contextlib import AsyncExitStack
from collections import Counter

import clr
clr.AddReference("ATK-DP100DLL(x64)")
from ATK_DP100DLL import ATKDP100API # type: ignore

class Power:
    def __init__(self, api: ATKDP100API, volt: float):
        self.api = api
        self.volt = int(volt * 1000)
    
    def __enter__(self):
        assert self.api.OpenOut(2, 100, self.volt)
        return self

    def __exit__(self, *exception):
        assert self.api.CloseOut(2, 100, self.volt)

async def main():
    async with AsyncExitStack() as stack:
        limit = 2 ** 20
        reader, writer = await asyncio.open_connection('192.168.31.129', 5025, limit=limit)
        stack.callback(writer.close)

        dbegin = datetime.now()
        tbegin = time.monotonic()
        def now(time_point: float):
            return dbegin + timedelta(seconds=time_point - tbegin)

        async def write(data: bytes | str):
            if isinstance(data, str):
                data = data.encode('utf-8')
            writer.write(data.strip() + b'\n')
            await writer.drain()
            print(f'write: {data}')

        async def query(cmd: bytes | str):
            prev = time.monotonic()
            await write(cmd)
            response = await reader.readline()
            after = time.monotonic()
            print(f'[query][{after - prev:.3f}s] {cmd} -> len {len(response)}, \\n {response.endswith(b"\n")}')
            return response.strip().decode()

        async def measure():
            volts: list[float] = []
            try:
                async with asyncio.timeout(3):
                    cmd = b'READ?'
                    prev = time.monotonic()
                    while True:
                        current, response = await query(cmd)
                        old_length = len(volts)
                        volts.extend(float(r) for r in response.split(','))
                        new_length = len(volts)
                        xnow = now(current)
                        elapsed = (current - prev) * 1000
                        print(f'[{xnow:%H:%M:%S}.{xnow.microsecond // 1000:03d}][{elapsed:.0f}ms] {cmd} -> {new_length - old_length}')
                        prev = current
            except TimeoutError:
                return volts

        api = ATKDP100API()
        assert api.DevOpenOrClose()

        def output():
            time.sleep(1.000)
            with Power(api, 3.5): time.sleep(1.000)
            
        async def external():
            res_opc = await query(b'INIT;*OPC?')
            print(res_opc)

            asyncio.ensure_future(asyncio.to_thread(output))

            volts: list[float] = []
            try:
                async with asyncio.timeout(5):
                    response = await query(b'FETCh?')
            except TimeoutError:
                await write(b'ABORt')
                return volts

            old_length = len(volts)
            volts.extend(float(r) for r in response.split(','))
            new_length = len(volts)
            print(f'[fetch] point count: {new_length - old_length}')

            return volts

        async def set_volt_range(volt: float):
            texts = ['200e-3', '2', '20', '200', '1000']
            for t in texts:
                r = float(t)
                if abs(volt) < r * 0.95:
                    await write(f'SENSe:CURRent:DC:RANGe {t}')
                    return
            raise Exception('测试电压超过万用表最大量程')

        plc_to_points = {
            0.001: 50000.0,
            0.01: 5000.0,
            0.1: 500.0,
            1.0: 50.0,
            10.0: 5.0,
            100.0: 0.5,
        }

        await write(b'ABORt')
        await write(b'VOLTage:NPLC 0.01')
        await write(b'CURRent:NPLC 0.01')
        await write(b'SAMPle:COUNt 9000')
        await write(b'TRIGger:SOURce EXTernal')
        await write(b'TRIGger:COUNt 1')
        await set_volt_range(14)
        print(f"OPC: {await query(b'*OPC?')}")

        while True:
            volts = await external()
            if not volts: continue
            duration = len(volts) / plc_to_points[0.01]
            print(f'{duration = }')
            
            mid = (max(volts) + min(volts)) / 2
            xtop, = Counter(v // 0.001 for v in volts if v >= mid).most_common(1)
            top, count = xtop
            print(f'top: {top * 0.001:.3f}V, {count = }')

            fig, ax = plt.subplots()
            ax.plot(np.linspace(0, duration, len(volts)), volts, '.-')
            ax.axhline(mid)
            plt.show()

        # async with asyncio.TaskGroup() as tg:
        #     fm = tg.create_task(xxx())
        #     # fm = tg.create_task(measure())
        #     tg.create_task(asyncio.to_thread(output))
        
        # volts = fm.result()
        # duration = len(volts) / plc_to_points[0.01]
        # print(f'{duration = }')
        
        # mid = (max(volts) + min(volts)) / 2
        # xtop, = Counter(v // 0.001 for v in volts if v >= mid).most_common(1)
        # top, count = xtop
        # print(f'top: {top * 0.001:.3f}V, {count = }')

        # fig, ax = plt.subplots()
        # ax.plot(np.linspace(0, duration, len(volts)), volts, '.-')
        # ax.axhline(mid)
        # plt.show()

if __name__ == '__main__':
    asyncio.run(main())
