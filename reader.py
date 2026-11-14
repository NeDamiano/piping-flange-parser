"""Read a PCF (Piping Component File) into plain Python data."""

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
    """One end of a component: its position and nominal size."""

    x: float
    y: float
    z: float
    bore: str  # kept as text: inch sizes can be written as fractions


@dataclass(eq=False)
class Component:
    """One block of the PCF: a pipe, a flange, a gasket, a bolt set..."""

    type: str
    end_points: list[EndPoint] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class PcfFile:
    """Everything read from one PCF file."""

    header: dict[str, str] = field(default_factory=dict)
    components: list[Component] = field(default_factory=list)
    materials: dict[str, str] = field(default_factory=dict)


def split_keyword(line: str) -> tuple[str, str]:
    """Split a PCF line into its keyword and its value."""
    # First word is the keyword, the rest (if any) is the value.
    parts = line.split(maxsplit=1)
    keyword = parts[0]
    value = parts[1] if len(parts) == 2 else ""
    return keyword, value


def parse_end_point(value: str) -> EndPoint:
    """Turn "x y z bore" into an EndPoint."""
    x, y, z, bore = value.split()[:4]
    return EndPoint(float(x), float(y), float(z), bore)


def add_component_line(component: Component, keyword: str, value: str) -> None:
    """Store one line of a component block as an end point or an attribute."""
    if keyword == "END-POINT":
        component.end_points.append(parse_end_point(value))
    else:
        component.attributes[keyword] = value


def add_description(materials: dict[str, str], item_code: str, text: str) -> None:
    """Attach a DESCRIPTION line to its ITEM-CODE in the materials table."""
    # A description can span several DESCRIPTION lines.
    if item_code in materials:
        materials[item_code] += " " + text
    else:
        materials[item_code] = text


def read_pcf(path: Path) -> PcfFile:
    """Read a PCF file and return its header, components and materials."""
    pcf = PcfFile()
    in_materials = False
    current_component = None    # the component being filled
    current_item_code = None    # last ITEM-CODE seen in MATERIALS

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        keyword, value = split_keyword(line)

        if keyword == "MATERIALS":
            in_materials = True
        elif in_materials:
            if keyword == "ITEM-CODE":
                current_item_code = value
            elif keyword == "DESCRIPTION" and current_item_code is not None:
                add_description(pcf.materials, current_item_code, value)
        elif keyword in COMPONENT_TYPES:
            current_component = Component(type=keyword)
            pcf.components.append(current_component)
        elif current_component is not None:
            add_component_line(current_component, keyword, value)
        else:
            pcf.header[keyword] = value

    return pcf


def print_summary(pcf: PcfFile) -> None:
    """Print what was read, for a quick visual check."""
    print("HEADER")
    for key, value in pcf.header.items():
        print(f"  {key}: {value}")

    print(f"COMPONENTS ({len(pcf.components)})")
    for component in pcf.components:
        positions = []
        for point in component.end_points:
            positions.append((point.x, point.y, point.z))
        print(f"  {component.type} {positions} {component.attributes}")

    print(f"MATERIALS ({len(pcf.materials)})")
    for item_code, description in pcf.materials.items():
        print(f"  {item_code}: {description}")


if __name__ == "__main__":
    print_summary(read_pcf(Path(sys.argv[1])))