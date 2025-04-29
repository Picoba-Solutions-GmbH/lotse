from dataclasses import dataclass


@dataclass
class VolumeMap:
    name: str
    path: str
    pvc_name: str
