"""Check the rebuilt joints and report what is missing or inconsistent."""

import sys
from dataclasses import dataclass
from pathlib import Path

from joints import Joint, build_joints, class_and_facing
from reader import Component, PcfFile, read_pcf


@dataclass
class Issue:
    """One finding on a joint: a short code and a readable message."""

    joint: Joint
    code: str
    message: str


def item_code_of(part: Component) -> str | None:
    """Return the item code of a part (bolts use their own keyword)."""
    if part.type == "BOLT":
        return part.attributes.get("BOLT-ITEM-CODE")
    return part.attributes.get("ITEM-CODE")


def parts_of(joint: Joint) -> list[Component]:
    """Return the parts of the joint that are present."""
    result = []
    for part in (joint.flange_a, joint.flange_b, joint.gasket, joint.bolt):
        if part is not None:
            result.append(part)
    return result


def check_unpaired_flange(joint: Joint, pcf: PcfFile) -> list[Issue]:
    """A flange with no mating flange in the file."""
    if joint.flange_b is None:
        message = "Flange has no mating flange in this file"
        return [Issue(joint, "UNPAIRED_FLANGE", message)]
    return []


def check_missing_gasket(joint: Joint, pcf: PcfFile) -> list[Issue]:
    """Two flanges bolted together with no gasket between them."""
    if joint.flange_b is not None and joint.gasket is None:
        message = "No gasket between the two flanges"
        return [Issue(joint, "MISSING_GASKET", message)]
    return []


def check_missing_bolts(joint: Joint, pcf: PcfFile) -> list[Issue]:
    """A joint with no bolt set."""
    if joint.bolt is None:
        return [Issue(joint, "MISSING_BOLTS", "No bolt set for this joint")]
    return []


def check_missing_description(joint: Joint, pcf: PcfFile) -> list[Issue]:
    """A part whose item code is absent or has no entry in MATERIALS."""
    issues = []
    reported_codes = []     # the two flanges often share the same item code
    for part in parts_of(joint):
        item_code = item_code_of(part)
        if item_code is None:
            message = f"{part.type} has no item code"
            issues.append(Issue(joint, "MISSING_ITEM_CODE", message))
        elif item_code not in pcf.materials and item_code not in reported_codes:
            message = f"Item code {item_code} has no description in MATERIALS"
            issues.append(Issue(joint, "MISSING_DESCRIPTION", message))
            reported_codes.append(item_code)
    return issues


def check_flange_mismatch(joint: Joint, pcf: PcfFile) -> list[Issue]:
    """Two mating flanges with a different pressure class or facing."""
    if joint.flange_b is None:
        return []
    class_a, facing_a = class_and_facing(joint.flange_a, pcf)
    class_b, facing_b = class_and_facing(joint.flange_b, pcf)

    issues = []
    if class_a is not None and class_b is not None and class_a != class_b:
        message = f"Flange classes differ: {class_a} and {class_b}"
        issues.append(Issue(joint, "CLASS_MISMATCH", message))
    if facing_a is not None and facing_b is not None and facing_a != facing_b:
        message = f"Flange facings differ: {facing_a} and {facing_b}"
        issues.append(Issue(joint, "FACING_MISMATCH", message))
    return issues


def digits_of(text: str | None) -> str:
    """Keep only the digits of a text: "150#" -> "150"."""
    result = ""
    if text is not None:
        for character in text:
            if character.isdigit():
                result += character
    return result


def check_line_class_mismatch(joint: Joint, pcf: PcfFile) -> list[Issue]:
    """A flange whose pressure class differs from the nominal class of the line."""
    line_class = digits_of(pcf.header.get("NOMINAL-CLASS"))
    if line_class == "":
        return []

    issues = []
    for label, flange in (("A", joint.flange_a), ("B", joint.flange_b)):
        if flange is None:
            continue
        flange_class, facing = class_and_facing(flange, pcf)
        if flange_class is not None and flange_class != line_class:
            message = (f"Flange {label} class {flange_class} differs from "
                       f"the line class {line_class}")
            issues.append(Issue(joint, "LINE_CLASS_MISMATCH", message))
    return issues


ALL_CHECKS = [
    check_unpaired_flange,
    check_missing_gasket,
    check_missing_bolts,
    check_missing_description,
    check_flange_mismatch,
    check_line_class_mismatch,
]


def check_joints(joints: list[Joint], pcf: PcfFile) -> list[Issue]:
    """Run every check on every joint and return all the issues found."""
    issues = []
    for joint in joints:
        for check in ALL_CHECKS:
            issues.extend(check(joint, pcf))
    return issues


def print_issues(issues: list[Issue], joints: list[Joint]) -> None:
    """Print the issues found, for a quick visual check."""
    if not issues:
        print("No issues found")
        return
    print(f"ISSUES ({len(issues)})")
    for issue in issues:
        number = joints.index(issue.joint) + 1
        print(f"  Joint {number} on line {issue.joint.line}: "
              f"{issue.code} - {issue.message}")


if __name__ == "__main__":
    pcf = read_pcf(Path(sys.argv[1]))
    joints = build_joints(pcf)
    print_issues(check_joints(joints, pcf), joints)
