# Read a PCF (Piping Component File) into plain Python data.


import sys
from dataclasses import dataclass, field
from pathlib import Path

# Keywords that open a new component block.
# Limit: a type missing from this set is read as an attribute of the
# previous component.
COMPONENT_TYPES = {
    "PIPE", "FLANGE", "FLANGE-BLIND", "GASKET", "BOLT",
    "ELBOW", "TEE", "VALVE", "REDUCER-CONCENTRIC", "REDUCER-ECCENTRIC",
    "CAP", "WELD",
}


@dataclass
class EndPoint:
    x: float
    y: float
    z: float
    bore: str  # kept as text: inch sizes can be written as fractions


@dataclass
class Component:
    type: str
    end_points: list[EndPoint] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class PcfFile:
    header: dict[str, str] = field(default_factory=dict)
    components: list[Component] = field(default_factory=list)
    materials: dict[str, str] = field(default_factory=dict)


def read_pcf(path: Path) -> PcfFile:
    pcf = PcfFile()
    section = "header"      # "header" -> "components" -> "materials"
    current = None          # the component being filled
    item_code = None        # last ITEM-CODE seen in MATERIALS

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # First word is the keyword, the rest (if any) is the value.
        parts = line.split(maxsplit=1)
        keyword = parts[0]
        value = parts[1] if len(parts) > 1 else ""

        if keyword == "MATERIALS":
            section = "materials"
        elif section == "materials":
            if keyword == "ITEM-CODE":
                item_code = value
            elif keyword == "DESCRIPTION" and item_code is not None:
                # A description can span several DESCRIPTION lines.
                previous = pcf.materials.get(item_code, "")
                pcf.materials[item_code] = (previous + " " + value).strip()
        elif keyword in COMPONENT_TYPES:
            section = "components"
            current = Component(type=keyword)
            pcf.components.append(current)
        elif section == "components":
            if keyword == "END-POINT":
                x, y, z, bore = value.split()[:4]
                current.end_points.append(
                    EndPoint(float(x), float(y), float(z), bore)
                )
            else:
                current.attributes[keyword] = value
        else:
            pcf.header[keyword] = value

    return pcf


if __name__ == "__main__":
    pcf = read_pcf(Path(sys.argv[1]))

    print("HEADER")
    for key, value in pcf.header.items():
        print(f"  {key}: {value}")

    print(f"COMPONENTS ({len(pcf.components)})")
    for component in pcf.components:
        points = [(p.x, p.y, p.z) for p in component.end_points]
        print(f"  {component.type} {points} {component.attributes}")

    print(f"MATERIALS ({len(pcf.materials)})")
    for code, description in pcf.materials.items():
        print(f"  {code}: {description}")