"""SQLite database helpers.

SQLite 관련 코드는 이 파일에만 모아 둡니다.
대시보드 화면(app.py)은 "어떤 테이블이 있나?", "테이블을 DataFrame으로 읽어 와라"
정도만 요청하고, 실제 SQL 처리 방식은 여기서 담당합니다.

초보자용 설명:
- SQLite는 하나의 .db 파일 안에 여러 table을 저장할 수 있습니다.
- pandas는 SQL query 결과를 DataFrame으로 바로 읽을 수 있습니다.
- 하지만 테이블 이름에 공백/점/특수문자가 있을 수 있으므로,
  quote_identifier()로 안전하게 감싸서 SQL을 만듭니다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def ensure_database_exists(db_path: Path) -> None:
    """DB 파일이 실제로 존재하는지 확인합니다."""

    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB file does not exist: {db_path}")


def connect_database(db_path: Path) -> sqlite3.Connection:
    """SQLite DB에 연결합니다.

    sqlite3.connect()는 파일이 없으면 새 DB를 만들어 버릴 수 있습니다.
    대시보드에서는 실수로 빈 DB를 만드는 일이 없도록 먼저 존재 여부를 확인합니다.
    """

    # sqlite3.connect()는 존재하지 않는 경로를 주면 빈 DB 파일을 새로 만들 수 있습니다.
    # 대시보드에서 그 동작은 실수에 가깝기 때문에 먼저 존재 여부를 확인합니다.
    ensure_database_exists(db_path)
    return sqlite3.connect(str(db_path))


def quote_identifier(identifier: str) -> str:
    """SQLite 테이블/컬럼 이름을 안전하게 감싸는 함수입니다.

    예: Max.SF, Heave Tn처럼 점이나 공백이 들어간 이름도 SQL에서 안전하게 쓸 수 있습니다.
    큰따옴표가 이름 안에 들어간 특수한 경우까지 처리합니다.
    """

    # SQLite에서 테이블명/컬럼명을 큰따옴표로 감싸면 공백이나 점이 있어도 안전합니다.
    # 이름 안에 큰따옴표가 들어간 특수한 경우는 큰따옴표를 두 번 써서 escaping합니다.
    return '"' + identifier.replace('"', '""') + '"'


def list_tables(db_path: Path) -> list[str]:
    """DB 안에 있는 사용자 테이블 목록을 가져옵니다."""

    # sqlite_master는 SQLite가 내부적으로 가지고 있는 메타데이터 테이블입니다.
    # 여기에서 type='table'인 항목만 가져오면 DB 안의 테이블 목록을 알 수 있습니다.
    # sqlite_%로 시작하는 테이블은 SQLite 내부용이므로 제외합니다.
    query = """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """
    with connect_database(db_path) as connection:
        rows = connection.execute(query).fetchall()
    return [row[0] for row in rows]


def validate_table_name(table_name: str, valid_tables: list[str]) -> None:
    """선택한 테이블명이 실제 DB 테이블 목록에 있는지 확인합니다."""

    if table_name not in valid_tables:
        raise ValueError(f"Table '{table_name}' was not found in the database.")


def load_table(db_path: Path, table_name: str) -> pd.DataFrame:
    """SQLite 테이블 하나를 pandas DataFrame으로 읽습니다."""

    # 사용자가 선택한 table_name을 그대로 SQL에 넣기 전에,
    # 실제 DB 안에 존재하는 테이블인지 확인합니다.
    valid_tables = list_tables(db_path)
    validate_table_name(table_name, valid_tables)

    # 테이블명이 Max.SF처럼 점을 포함하거나 공백을 포함해도 읽을 수 있게 quote합니다.
    query = f"SELECT * FROM {quote_identifier(table_name)}"
    with connect_database(db_path) as connection:
        return pd.read_sql_query(query, connection)
