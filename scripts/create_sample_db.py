"""Create a sample SQLite DB for the FPSO dashboard.

실행:
    python scripts/create_sample_db.py

실제 계산 DB가 아직 없을 때 대시보드 화면을 먼저 확인하기 위한 샘플입니다.
데이터는 임의 공식으로 만든 예시값이므로 설계 판단에는 사용하면 안 됩니다.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "fpso_results_sample.sqlite"


def parse_args() -> argparse.Namespace:
    """명령줄 옵션을 읽습니다."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="생성할 SQLite DB 파일 경로",
    )
    return parser.parse_args()


def create_connection(db_path: Path) -> sqlite3.Connection:
    """SQLite 연결을 만들고, 부모 폴더가 없으면 먼저 생성합니다."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(db_path))


def drop_existing_table(connection: sqlite3.Connection) -> None:
    """같은 이름의 샘플 테이블이 있으면 지웁니다."""

    connection.execute("DROP TABLE IF EXISTS fpso_results")


def create_results_table(connection: sqlite3.Connection) -> None:
    """대시보드가 읽을 샘플 결과 테이블을 생성합니다."""

    connection.execute(
        """
        CREATE TABLE fpso_results (
            "L" REAL,
            "B" REAL,
            "D" REAL,
            "T" REAL,
            "LC" TEXT,
            "GM" REAL,
            "Max.SF" REAL,
            "Max.BM" REAL,
            "Heave Tn" REAL,
            "Roll Tn" REAL,
            "Pitch Tn" REAL,
            "Heave MPM" REAL,
            "Roll MPM" REAL,
            "Pitch MPM" REAL
        )
        """
    )


def calculate_sample_row(
    length: float,
    breadth: float,
    depth: float,
    draft: float,
    loading_condition: str,
) -> tuple:
    """L/B/D/T/LC 조합 하나에 대한 임의 결과값을 만듭니다."""

    condition_factor = {
        "Ballast": 0.86,
        "PartialLoad": 0.95,
        "FullLoad": 1.08,
    }[loading_condition]

    noise = random.uniform(-0.04, 0.04)
    gm = round((breadth / 11.5) - (draft / 8.0) + condition_factor + noise, 3)
    max_sf = round(length * breadth * draft * condition_factor / 115.0, 2)
    max_bm = round(length**2 * breadth * condition_factor / 980.0, 2)
    heave_tn = round(0.18 * (draft**0.5) + 0.018 * breadth, 3)
    roll_tn = round(2.35 * breadth / max(gm, 0.5), 3)
    pitch_tn = round(0.038 * length + 0.12 * draft, 3)
    heave_mpm = round(0.45 + 0.003 * length - 0.004 * breadth + noise, 3)
    roll_mpm = round(1.20 + 0.010 * breadth - 0.090 * gm - noise, 3)
    pitch_mpm = round(0.75 + 0.002 * length - 0.020 * draft + noise, 3)

    return (
        length,
        breadth,
        depth,
        draft,
        loading_condition,
        gm,
        max_sf,
        max_bm,
        heave_tn,
        roll_tn,
        pitch_tn,
        heave_mpm,
        roll_mpm,
        pitch_mpm,
    )


def build_sample_rows() -> list[tuple]:
    """여러 L/B/D/T/LC 조합의 샘플 행을 만듭니다."""

    random.seed(7)

    lengths = [300.0, 335.0, 370.0]
    breadths = [58.0, 65.0, 72.0]
    depths = [28.0, 32.0]
    drafts = [10.5, 12.0, 14.0]
    loading_conditions = ["Ballast", "PartialLoad", "FullLoad"]

    rows = []
    for length in lengths:
        for breadth in breadths:
            for depth in depths:
                for draft in drafts:
                    for loading_condition in loading_conditions:
                        rows.append(
                            calculate_sample_row(
                                length,
                                breadth,
                                depth,
                                draft,
                                loading_condition,
                            )
                        )
    return rows


def insert_rows(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    """계산된 샘플 행들을 DB에 저장합니다."""

    connection.executemany(
        """
        INSERT INTO fpso_results (
            "L",
            "B",
            "D",
            "T",
            "LC",
            "GM",
            "Max.SF",
            "Max.BM",
            "Heave Tn",
            "Roll Tn",
            "Pitch Tn",
            "Heave MPM",
            "Roll MPM",
            "Pitch MPM"
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def create_sample_database(db_path: Path) -> None:
    """샘플 DB 전체 생성 작업을 순서대로 실행합니다."""

    with create_connection(db_path) as connection:
        drop_existing_table(connection)
        create_results_table(connection)
        insert_rows(connection, build_sample_rows())
        connection.commit()


def main() -> None:
    """스크립트 진입점입니다."""

    args = parse_args()
    create_sample_database(args.output)
    print(f"Sample DB created: {args.output}")


if __name__ == "__main__":
    main()
