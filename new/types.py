from typing import Literal
from dataclasses import dataclass, asdict

@dataclass
class Devices:
    dmms: list[str]
    power1: str
    power2: str
    resist: str

@dataclass
class ReferArgument:
    name: str
    type: Literal['NPN', 'PNP']
    duration: float
    Vc_max: float
    Ve_max: float
    targets: list[tuple[float, float]]

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

    def tuple(self): 
        return [
            f'{self.target_Vce:.3f}',
            f'{self.target_Ic:.6f}',
            f'{self.Vce:.3f}',
            f'{self.Ic:.6f}',
            f'{self.Vc:.3f}',
            f'{self.Ve:.3f}',
            f'{self.Rc}',
            f'{self.Re}',
        ]
    
    def dict(self):
        return asdict(self)

@dataclass
class ExecItem:
    Vce: float
    Ic: float
    Vc: float
    Ve: float
    duration: float
    
@dataclass
class ExecArgument:
    name: str
    type: Literal['NPN', 'PNP']
    Vc_max: float
    Ve_max: float
    items: list[ExecItem]
