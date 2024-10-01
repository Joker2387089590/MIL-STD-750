import asyncio, traceback, math
from dataclasses import dataclass
from contextlib import ExitStack
from PySide6.QtCore import QObject, Signal, Slot
from PySide6 import QtAsyncio
from .resist import Resist
from .dmm import Meter
from .power import Power

@dataclass
class Argument:
    Vce: float
    Ic: float
    Pmax: float
    Vb_max: float
    Vc_max: float

@dataclass
class State:
    Vb: float
    Vc: float

class Device(QObject):
    def __init__(self, resist, dmm, power_vb, power_vc) -> None:
        super().__init__(None)
        with ExitStack() as stack:
            self.resist = Resist(resist, self); stack.callback(self.resist.disconnects)
            self.dmm = Meter(dmm); stack.callback(self.dmm.disconnects)
            self.power_vb = Power(power_vb); stack.callback(self.power_vb.disconnects)
            self.power_vc = Power(power_vc); stack.callback(self.power_vc.disconnects)
            self.power_vc.set_current_protection(40 * 0.6) # 继电器
            self._disconnects = stack.pop_all()
    
    def disconnects(self):
        self._disconnects.close()
        self.deleteLater()

class Context(QObject):
    paused = Signal()
    pointTested = Signal(float, float, float, float) # Vb, Vc, Vce, Ic
    vbStarted = Signal(float)

    def __init__(self, arg: Argument, dev: Device) -> None:
        super().__init__(None)
        self.arg = arg
        self.dev = dev
        self.mapping: dict[tuple[float, float], tuple[float, float]] = {}

    def test(self, Vb: float, Vc: float):
        pair = (Vb, Vc)
        if pair in self.mapping: return self.mapping[pair]
        Vce, Ic = self.test_without_cache(Vb, Vc)
        self.mapping[pair] = (Vce, Ic)
        self.pointTested.emit(Vb, Vc, Vce, Ic)
        
    def test_without_cache(self, Vb: float, Vc: float):
        if Vb > self.arg.Vb_max: raise Exception('Vb 超出限值')
        if Vc > self.arg.Vc_max: raise Exception('Vc 超出限值')

        self.dev.power_vc.set_voltage(Vc)
        self.dev.power_vb.set_voltage(Vb)

        with self.dev.power_vc, self.dev.power_vb:
            return self.dev.dmm.read_dc_volt(), self.dev.dmm.read_dc_current()

    @Slot()
    def run(self):
        try:
            self.pause_event = asyncio.Event()
            self.stop_event = asyncio.Event()
            QtAsyncio.run(self._run(), keep_running=False, quit_qapp=False)
            self.deleteLater()
        except:
            traceback.print_exc()

    async def _run(self):
        try:
            self.dev.power_vb.reconfig()
            self.dev.power_vc.reconfig()
            self.dev.dmm.reconfig()

            # await self.search_resist()
            await self.fill_cache()
        except KeyboardInterrupt:
            pass
        except:
            traceback.print_exc()
        finally:
            pass

    async def search_resist(self):
        Vc = self.arg.Vce * 0.50
        for ib in range(2, 8):
            Vb = self.arg.Vb_max * ib / 10
            for res in [100e3, 10e3, 1e3, 100, 10, 1]:
                self.dev.resist.set_value(res)
                Vce, Ic = self.test_without_cache(Vb, Vc)
                if Vce > self.arg.Vce * 0.10: return
                if Ic > self.arg.Ic * 0.5: return

    async def fill_cache(self):
        step_Vc = 10 ** (max(int(math.log(self.arg.Vce, 10)) - 1, -2))
        step_Vb = 10 ** (max(int(math.log(self.arg.Vb_max, 10)) - 1, -2))
        Vb = step_Vb
        Vc = step_Vc
        while True:
            self.vbStarted.emit(Vb)
            Vce, Ic = self.test(Vb, Vc)
            if Ic < self.arg.Ic and Vce < self.arg.Vce and Vce * Ic < self.arg.Pmax:
                Vc += step_Vc
            else:
                Vb += step_Vb
                Vc = step_Vc

    @Slot()
    def pause(self):
        if self.pause_event:
            self.pause_event.set()

    @Slot()
    def stop(self):
        if self.stop_event:
            self.stop_event.set()
