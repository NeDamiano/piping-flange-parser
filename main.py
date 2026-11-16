"""Run the whole pipeline: read PCF files, rebuild and check the joints,
store them in the database and export two CSV reports."""

import argparse
import csv
import sqlite3
from pathlib import Path

from checks import check_joints
from db import open_database, save_pcf
from joints import build_joints
from reader import read_pcf

# One row per joint, in the shape of a joint register.
# Each LEFT JOIN picks the component with one role, so a missing part
# simply leaves its columns empty.
JOINT_REGISTER_QUERY = """
SELECT
    j.line_reference,
    j.id,
    j.x, j.y, j.z,
    flange_a.item_code, item_a.pressure_class, item_a.facing,
    flange_b.item_code, item_b.pressure_class, item_b.facing,
    gasket.item_code,
    bolts.item_code, bolts.size, bolts.length, bolts.quantity,
    (SELECT COUNT(*) FROM issues WHERE issues.joint_id = j.id)
FROM joints AS j
LEFT JOIN joint_components AS flange_a
       ON flange_a.joint_id = j.id AND flange_a.role = 'FLANGE_A'
LEFT JOIN items AS item_a ON item_a.item_code = flange_a.item_code
LEFT JOIN joint_components AS flange_b
       ON flange_b.joint_id = j.id AND flange_b.role = 'FLANGE_B'
LEFT JOIN items AS item_b ON item_b.item_code = flange_b.item_code
LEFT JOIN joint_components AS gasket
       ON gasket.joint_id = j.id AND gasket.role = 'GASKET'
LEFT JOIN joint_components AS bolts
       ON bolts.joint_id = j.id AND bolts.role = 'BOLTS'
ORDER BY j.line_reference, j.id
"""

JOINT_REGISTER_COLUMNS = [
    "line", "joint_id", "x", "y", "z",
    "flange_a_item", "flange_a_class", "flange_a_facing",
    "flange_b_item", "flange_b_class", "flange_b_facing",
    "gasket_item",
    "bolt_item", "bolt_diameter", "bolt_length", "bolt_quantity",
    "issue_count",
]

ISSUES_QUERY = """
SELECT j.line_reference, issues.joint_id, issues.code, issues.message
FROM issues
JOIN joints AS j ON j.id = issues.joint_id
ORDER BY j.line_reference, issues.joint_id, issues.id
"""

ISSUES_COLUMNS = ["line", "joint_id", "code", "message"]


def load_file(connection: sqlite3.Connection, pcf_path: Path) -> None:
    """Run the pipeline on one PCF file and print a one-line summary."""
    pcf = read_pcf(pcf_path)
    joints = build_joints(pcf)
    issues = check_joints(joints, pcf)
    save_pcf(connection, pcf, joints, issues, pcf_path.name)
    print(f"{pcf_path.name}: {len(joints)} joints, {len(issues)} issues")


def export_csv(connection: sqlite3.Connection, query: str, columns: list[str],
               csv_path: Path) -> int:
    """Write the result of a query to a CSV file and return the row count."""
    rows = connection.execute(query).fetchall()
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
    return len(rows)


def parse_arguments() -> argparse.Namespace:
    """Read the command line: PCF files, database path, output folder."""
    parser = argparse.ArgumentParser(
        description="Build a flanged joint database from PCF files.")
    parser.add_argument("pcf_files", nargs="+", type=Path,
                        help="one or more PCF files to load")
    parser.add_argument("--db", type=Path, default=Path("flanges.db"),
                        help="SQLite database file (default: flanges.db)")
    parser.add_argument("--out", type=Path, default=Path("out"),
                        help="folder for the CSV reports (default: out)")
    return parser.parse_args()


def main() -> None:
    """Load every file given on the command line, then export the reports."""
    arguments = parse_arguments()
    connection = open_database(arguments.db)

    for pcf_path in arguments.pcf_files:
        if pcf_path.exists():
            load_file(connection, pcf_path)
        else:
            print(f"{pcf_path}: file not found, skipped")

    arguments.out.mkdir(exist_ok=True)
    joints_csv = arguments.out / "joints.csv"
    issues_csv = arguments.out / "issues.csv"
    joint_count = export_csv(
        connection, JOINT_REGISTER_QUERY, JOINT_REGISTER_COLUMNS, joints_csv)
    issue_count = export_csv(
        connection, ISSUES_QUERY, ISSUES_COLUMNS, issues_csv)
    connection.close()

    print(f"Database: {arguments.db}")
    print(f"{joints_csv}: {joint_count} joints")
    print(f"{issues_csv}: {issue_count} issues")


if __name__ == "__main__":
    main()
