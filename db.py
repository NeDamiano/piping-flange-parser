"""Store lines, items, joints, components and issues in a SQLite database."""

import sqlite3
import sys
from pathlib import Path

from checks import Issue, check_joints, item_code_of
from joints import Joint, build_joints, joint_position, parse_description
from reader import Component, PcfFile, read_pcf

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def open_database(path: Path) -> sqlite3.Connection:
    """Open the database and create the tables if they do not exist."""
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")   # off by default in SQLite
    connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    return connection


def to_integer(text: str | None) -> int | None:
    """Keep only the digits of a text: "150#" -> 150. None if there are none."""
    if text is None:
        return None
    digits = ""
    for character in text:
        if character.isdigit():
            digits += character
    if digits == "":
        return None
    return int(digits)


def to_number(text: str | None) -> float | None:
    """Turn a text into a number, or None if it is not a plain number."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def delete_line(connection: sqlite3.Connection, reference: str) -> None:
    """Remove a line and everything below it, so a file can be loaded again."""
    joints_of_line = "SELECT id FROM joints WHERE line_reference = ?"
    connection.execute(
        f"DELETE FROM issues WHERE joint_id IN ({joints_of_line})", (reference,))
    connection.execute(
        f"DELETE FROM joint_components WHERE joint_id IN ({joints_of_line})",
        (reference,))
    connection.execute("DELETE FROM joints WHERE line_reference = ?", (reference,))
    connection.execute("DELETE FROM lines WHERE reference = ?", (reference,))


def save_line(connection: sqlite3.Connection, pcf: PcfFile, source_file: str) -> str:
    """Insert the line described by the PCF header and return its reference."""
    reference = pcf.header.get("PIPELINE-REFERENCE", source_file)
    connection.execute(
        "INSERT INTO lines (reference, piping_spec, nominal_class, bore_units,"
        " coordinate_units, source_file) VALUES (?, ?, ?, ?, ?, ?)",
        (
            reference,
            pcf.header.get("PIPING-SPEC"),
            to_integer(pcf.header.get("NOMINAL-CLASS")),
            pcf.header.get("UNITS-BORE"),
            pcf.header.get("UNITS-CO-ORDS"),
            source_file,
        ),
    )
    return reference


def save_item(connection: sqlite3.Connection, item_code: str,
              description: str | None) -> None:
    """Add an item code to the catalog, or fill in its description."""
    pressure_class, facing = parse_description(description)
    values = (description, to_integer(pressure_class), facing, item_code)
    found = connection.execute(
        "SELECT 1 FROM items WHERE item_code = ?", (item_code,)).fetchone()
    if found is None:
        connection.execute(
            "INSERT INTO items (description, pressure_class, facing, item_code)"
            " VALUES (?, ?, ?, ?)", values)
    elif description is not None:
        connection.execute(
            "UPDATE items SET description = ?, pressure_class = ?, facing = ?"
            " WHERE item_code = ?", values)


def component_size(part: Component) -> str | None:
    """Return the nominal size of a part: bore, or bolt diameter."""
    if part.type == "BOLT":
        return part.attributes.get("BOLT-DIA")
    if part.end_points:
        return part.end_points[0].bore
    return None


def end_point_coordinates(part: Component, index: int) -> tuple:
    """Return (x, y, z) of the end point at the given index, or three Nones."""
    if index < len(part.end_points):
        point = part.end_points[index]
        return (point.x, point.y, point.z)
    return (None, None, None)


def save_component(connection: sqlite3.Connection, joint_id: int, role: str,
                   part: Component, pcf: PcfFile) -> None:
    """Insert one part of a joint, adding its item code to the catalog first."""
    item_code = item_code_of(part)
    if item_code is not None:
        save_item(connection, item_code, pcf.materials.get(item_code))
    connection.execute(
        "INSERT INTO joint_components (joint_id, role, component_type, item_code,"
        " skey, size, length, quantity, x1, y1, z1, x2, y2, z2)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            joint_id,
            role,
            part.type,
            item_code,
            part.attributes.get("SKEY"),
            component_size(part),
            to_number(part.attributes.get("BOLT-LENGTH")),
            to_integer(part.attributes.get("BOLT-QUANTITY")),
            *end_point_coordinates(part, 0),
            *end_point_coordinates(part, 1),
        ),
    )


def save_joint(connection: sqlite3.Connection, joint: Joint, reference: str,
               pcf: PcfFile) -> int:
    """Insert a joint with its components and return the new joint id."""
    position = joint_position(joint)
    if position is None:
        coordinates = (None, None, None)
    else:
        coordinates = (position.x, position.y, position.z)
    cursor = connection.execute(
        "INSERT INTO joints (line_reference, x, y, z) VALUES (?, ?, ?, ?)",
        (reference, *coordinates))
    joint_id = cursor.lastrowid

    roles = (
        ("FLANGE_A", joint.flange_a),
        ("FLANGE_B", joint.flange_b),
        ("GASKET", joint.gasket),
        ("BOLTS", joint.bolt),
    )
    for role, part in roles:
        if part is not None:
            save_component(connection, joint_id, role, part, pcf)
    return joint_id


def save_issue(connection: sqlite3.Connection, joint_id: int, issue: Issue) -> None:
    """Insert one finding of the checks."""
    connection.execute(
        "INSERT INTO issues (joint_id, code, message) VALUES (?, ?, ?)",
        (joint_id, issue.code, issue.message))


def save_pcf(connection: sqlite3.Connection, pcf: PcfFile, joints: list[Joint],
             issues: list[Issue], source_file: str) -> None:
    """Store one PCF file: its line, joints, components and issues."""
    reference = pcf.header.get("PIPELINE-REFERENCE", source_file)
    delete_line(connection, reference)
    save_line(connection, pcf, source_file)

    # The whole MATERIALS section goes into the catalog.
    for item_code, description in pcf.materials.items():
        save_item(connection, item_code, description)

    for joint in joints:
        joint_id = save_joint(connection, joint, reference, pcf)
        for issue in issues:
            if issue.joint is joint:
                save_issue(connection, joint_id, issue)
    connection.commit()


def print_row_counts(connection: sqlite3.Connection) -> None:
    """Print how many rows each table holds, for a quick visual check."""
    for table in ("lines", "items", "joints", "joint_components", "issues"):
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")


if __name__ == "__main__":
    pcf_path = Path(sys.argv[1])
    database_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("flanges.db")

    pcf = read_pcf(pcf_path)
    joints = build_joints(pcf)
    issues = check_joints(joints, pcf)

    connection = open_database(database_path)
    save_pcf(connection, pcf, joints, issues, pcf_path.name)
    print(f"Loaded {pcf_path.name} into {database_path}")
    print_row_counts(connection)
    connection.close()
