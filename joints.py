"""Rebuild flanged joints (two flanges, a gasket, a bolt set) from PCF components."""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from reader import Component, EndPoint, PcfFile, read_pcf

FLANGE_TYPES = {"FLANGE", "FLANGE-BLIND"}
POSITION_TOLERANCE = 0.01


@dataclass
class Joint:
    """A flanged joint: two flanges, a gasket and a bolt set (some may be missing)."""

    line: str  # PIPELINE-REFERENCE of the file
    flange_a: Component
    flange_b: Component | None = None
    gasket: Component | None = None
    bolt: Component | None = None

    def contains(self, component: Component) -> bool:
        """True if the component is a flange or the gasket of this joint."""
        return component in (self.flange_a, self.flange_b, self.gasket)


def same_point(p: EndPoint, q: EndPoint) -> bool:
    """True if two end points are in the same position (within tolerance)."""
    return (
        abs(p.x - q.x) <= POSITION_TOLERANCE
        and abs(p.y - q.y) <= POSITION_TOLERANCE
        and abs(p.z - q.z) <= POSITION_TOLERANCE
    )


def touching(a: Component, b: Component) -> bool:
    """True if the two components share at least one end point."""
    for p in a.end_points:
        for q in b.end_points:
            if same_point(p, q):
                return True
    return False


def joint_containing(component: Component, joints: list[Joint]) -> Joint | None:
    """Return the joint this flange or gasket belongs to, if any."""
    for joint in joints:
        if joint.contains(component):
            return joint
    return None


def unpaired(flanges: list[Component], joints: list[Joint]) -> list[Component]:
    """Return the flanges that are not part of any joint yet."""
    result = []
    for flange in flanges:
        if joint_containing(flange, joints) is None:
            result.append(flange)
    return result


def flanges_touching(component: Component, flanges: list[Component]) -> list[Component]:
    """Return the flanges that share an end point with the component."""
    result = []
    for flange in flanges:
        if flange is not component and touching(flange, component):
            result.append(flange)
    return result


def components_of_type(components: list[Component], types: set[str]) -> list[Component]:
    """Return the components whose type is one of the given types."""
    result = []
    for component in components:
        if component.type in types:
            result.append(component)
    return result


def add_joints_around_gaskets(joints, line, flanges, gaskets) -> None:
    """Create a joint for each gasket, with the flanges touching it."""
    # Start from the gaskets: each one sits between two flanges.
    for gasket in gaskets:
        mates = flanges_touching(gasket, unpaired(flanges, joints))
        if not mates:
            continue  # gasket with no flange next to it: ignored
        flange_a = mates[0]
        flange_b = mates[1] if len(mates) > 1 else None
        joints.append(Joint(line, flange_a, flange_b, gasket))


def add_joints_without_gasket(joints, line, flanges) -> None:
    """Create joints for the flanges that no gasket has claimed."""
    # Flanges left over: paired directly (no gasket) or alone.
    for flange in flanges:
        if joint_containing(flange, joints) is not None:
            continue
        mates = flanges_touching(flange, unpaired(flanges, joints))
        flange_b = mates[0] if mates else None
        joints.append(Joint(line, flange, flange_b))


def assign_bolts_by_file_order(joints, components) -> None:
    """Give each BOLT block to the joint that precedes it in the file."""
    # Bolts have no coordinates: a BOLT block goes to the joint of the
    # last flange or gasket that comes before it in the file.
    latest_joint = None
    for component in components:
        if component.type == "BOLT":
            if latest_joint is not None and latest_joint.bolt is None:
                latest_joint.bolt = component
        else:
            latest_joint = joint_containing(component, joints) or latest_joint


def build_joints(pcf: PcfFile) -> list[Joint]:
    """Rebuild all the flanged joints of a PCF file."""
    line = pcf.header.get("PIPELINE-REFERENCE", "")
    flanges = components_of_type(pcf.components, FLANGE_TYPES)
    gaskets = components_of_type(pcf.components, {"GASKET"})

    joints: list[Joint] = []
    add_joints_around_gaskets(joints, line, flanges, gaskets)
    add_joints_without_gasket(joints, line, flanges)
    assign_bolts_by_file_order(joints, pcf.components)
    return joints


def joint_position(joint: Joint) -> EndPoint | None:
    """Return the point where flange A meets the gasket (or flange B)."""
    neighbour = joint.gasket
    if neighbour is None:
        neighbour = joint.flange_b
    if neighbour is None:
        return None
    for p in joint.flange_a.end_points:
        for q in neighbour.end_points:
            if same_point(p, q):
                return p
    return None


def parse_description(description: str | None) -> tuple[str | None, str | None]:
    """Return (pressure_class, facing): "FLANGE WN 150# RF" -> ("150", "RF")."""
    if not description:
        return None, None
    pressure_class = re.search(r"(\d+)#", description)
    facing = re.search(r"\b(RF|FF|RTJ)\b", description)
    return (
        pressure_class.group(1) if pressure_class else None,
        facing.group(1) if facing else None,
    )


def class_and_facing(component: Component, pcf: PcfFile):
    """Look up the component's ITEM-CODE in MATERIALS and parse it."""
    item_code = component.attributes.get("ITEM-CODE")
    return parse_description(pcf.materials.get(item_code))


def describe_part(part: Component | None, pcf: PcfFile) -> str:
    """Return a one-line text for a joint part, or MISSING."""
    if part is None:
        return "MISSING"
    if part.type == "BOLT":
        quantity = part.attributes.get("BOLT-QUANTITY")
        diameter = part.attributes.get("BOLT-DIA")
        return f"{quantity} x {diameter}"
    item_code = part.attributes.get("ITEM-CODE")
    pressure_class, facing = class_and_facing(part, pcf)
    return f"{item_code} class={pressure_class} facing={facing}"


def print_joints(joints: list[Joint], pcf: PcfFile) -> None:
    """Print the joints found, for a quick visual check."""
    print(f"JOINTS ({len(joints)})")
    for number, joint in enumerate(joints, start=1):
        print(f"  Joint {number} on line {joint.line}")
        print(f"    flange A: {describe_part(joint.flange_a, pcf)}")
        print(f"    flange B: {describe_part(joint.flange_b, pcf)}")
        print(f"    gasket: {describe_part(joint.gasket, pcf)}")
        print(f"    bolts: {describe_part(joint.bolt, pcf)}")


if __name__ == "__main__":
    pcf = read_pcf(Path(sys.argv[1]))
    print_joints(build_joints(pcf), pcf)
