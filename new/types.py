from typing import Literal, Any
from dataclasses import dataclass, asdict

@dataclass
class Devices:
    dmms: list[str]
    power1: str
    power2: str
    resist: str

@dataclass
class ReferTarget:
    Vce: float
    Ic: float
    Rc: str
    Re: str

@dataclass
class ReferArgument:
    name: str
    type: Literal['NPN', 'PNP']
    
    duration: float
    stable_duration: float

    Vc_max: float
    Ve_max: float
    Vceo: float
    Vcbo: float
    Vebo: float

    targets: list[ReferTarget]

    @classmethod
    def fromdict(cls, data: dict[str, Any]):
        return cls(
            name=data.get('name', 'test'),
            type=data.get('type', 'NPN'),
            duration=data.get('duration', 1.0),
            stable_duration=data.get('stable_duration', 10.0),
            Vc_max=data.get('Vc_max', 200.0),
            Ve_max=data.get('Ve_max', 200.0),
            Vceo=data.get('Vceo', 200.0),
            Vcbo=data.get('Vcbo', 200.0),
            Vebo=data.get('Vebo', 200.0),
            targets=[ReferTarget(**t) for t in data.get('targets', [])],
        )

@dataclass
class ReferResult:
    target_Vce: float
    target_Ic: float
    
    Vce: float
    Ic: float

    Vc: float
    Ve: float
    Rc: str
    Re: str

    Vc_delay: float
    Ve_delay: float

    all_vce: list[float]
    all_dmm2: list[float]
    all_dmm3: list[float]
    all_ic: list[float]
    all_ie: list[float]

    def tuple(self): 
        return [
            f'{self.target_Vce:.3f}',
            f'{self.target_Ic:.6f}',
            f'{self.Vce:.3f}',
            f'{self.Ic:.6f}',
            f'{self.Vc:.3f}',
            f'{self.Ve:.3f}',
            f'{self.Ve - self.Ic * float(self.Rc.replace("k", "e3"))}',
            f'{self.Rc}',
            f'{self.Re}',
            f'{self.Vc_delay:.3f}',
            f'{self.Ve_delay:.3f}',
        ]
    
    def dict(self):
        return asdict(self)

    
@dataclass
class ReferAllResult:
    argument: ReferArgument
    results: list[ReferResult]

Measurement = Literal['Vce', 'Vcb', 'Vbe', 'Ic', 'Ie']

@dataclass
class ReferTargetResult:
    target_Vce: float
    target_Ic: float
    
    Vce: float
    Ic: float

    Vc: float
    Ve: float
    Rc: str
    Re: str

    Vc_delay: float
    Ve_delay: float

    measurements: dict[Measurement, list[float]]

    def tuple(self): 
        return [
            f'{self.target_Vce:.3f}',
            f'{self.target_Ic:.6f}',
            f'{self.Vce:.3f}',
            f'{self.Ic:.6f}',
            f'{self.Vc:.3f}',
            f'{self.Ve:.3f}',
            f'{self.Ve - self.Ic * float(self.Rc.replace("k", "e3"))}',
            f'{self.Rc}',
            f'{self.Re}',
            f'{self.Vc_delay:.3f}',
            f'{self.Ve_delay:.3f}',
        ]
    
    def dict(self):
        return asdict(self)

@dataclass
class ReferResults:
    argument: ReferArgument
    results: list[ReferTargetResult]

@dataclass
class ExecItem:
    Vce: float
    Ic: float
    Vc: float
    Ve: float
    Rc: str
    Re: str
    refer_Vce: float
    refer_Ic: float
    duration: float
    Ve_delay: float
    
@dataclass
class ExecArgument:
    name: str
    type: Literal['NPN', 'PNP']
    items: list[ExecItem]
    Vceo: float
    Vcbo: float
    Vebo: float

    @classmethod
    def fromdict(cls, data: dict):
        xitems = []
        items = data.get('items', [])
        for item in items:
            xitems.append(ExecItem(**item))

        return cls(
            name = data.get('name', 'test'),
            type = data.get('type', 'NPN'),
            Vceo = data.get('Vceo', 200.0),
            Vcbo = data.get('Vcbo', 200.0),
            Vebo = data.get('Vebo', 200.0),
            items = xitems,
        )

@dataclass
class ExecResult:
    type: Literal['NPN', 'PNP']
    item: ExecItem
    rate: float
    ve_start: float
    ve_stop: float
    output_stop: float
    all_vce: list[float]
    all_dmm2: list[float]
    all_dmm3: list[float]
    all_ic: list[float]
    all_ie: list[float]
    
    def mapping(self, time: float):
        return int((time) * self.rate)
    
    def output_range(self):
        return self.mapping(self.ve_stop), self.mapping(self.output_stop)

    def pass_fail(self, values: list[float]):
        if not values: return False
        avg = sum(values) / len(values)
        return min(values) > avg * 0.9 and max(values) < avg * 1.1
        
@dataclass
class ExecAllResult:
    results: list[ExecResult]
