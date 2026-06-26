"""Database-backed evaluation metadata repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, delete, insert, select, update

from finlongrag.db.base import JSONVariant
from finlongrag.db.session import get_sync_engine, get_sync_sessionmaker
from finlongrag.evaluation_center.schemas import EvalReport, TestSet

metadata = MetaData()

test_sets_table = Table(
    "evaluation_test_sets",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("sheet_names", JSONVariant, nullable=False, default=list),
    Column("file_name", String(500), nullable=False, default=""),
    Column("file_path", Text, nullable=False, default=""),
    Column("count", Integer, nullable=False, default=0),
    Column("created_at", String(64), nullable=False),
)

eval_runs_table = Table(
    "evaluation_runs",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("kb_id", String(64), nullable=False),
    Column("kb_name", String(255), nullable=False, default=""),
    Column("test_set_id", String(32), nullable=False),
    Column("test_set_name", String(255), nullable=False, default=""),
    Column("strategy", String(32), nullable=False),
    Column("top_k", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("metrics", JSONVariant, nullable=False, default=dict),
    Column("details", JSONVariant, nullable=False, default=list),
    Column("error_message", Text, nullable=False, default=""),
    Column("progress_current", Integer, nullable=False, default=0),
    Column("progress_total", Integer, nullable=False, default=0),
    Column("created_at", String(64), nullable=False),
    Column("finished_at", String(64), nullable=False, default=""),
)


class EvaluationRepository:
    def __init__(self, database_url: str) -> None:
        metadata.create_all(get_sync_engine(database_url), checkfirst=True)
        self._sessionmaker = get_sync_sessionmaker(database_url)

    def save_test_set(self, test_set: TestSet, *, file_path: str) -> TestSet:
        record = test_set.model_dump()
        record.pop("items", None)
        record["file_path"] = file_path
        with self._sessionmaker() as session:
            session.execute(insert(test_sets_table).values(**record))
            session.commit()
        return test_set

    def list_test_sets(self) -> list[dict[str, Any]]:
        with self._sessionmaker() as session:
            rows = session.execute(select(test_sets_table).order_by(test_sets_table.c.created_at.desc())).mappings().all()
        return [_public_test_set(dict(row)) for row in rows]

    def get_test_set(self, test_set_id: str) -> dict[str, Any] | None:
        row = self.get_test_set_record(test_set_id)
        return _public_test_set(row) if row else None

    def get_test_set_record(self, test_set_id: str) -> dict[str, Any] | None:
        with self._sessionmaker() as session:
            row = session.execute(select(test_sets_table).where(test_sets_table.c.id == test_set_id)).mappings().first()
        return dict(row) if row else None

    def delete_test_set(self, test_set_id: str) -> bool:
        with self._sessionmaker() as session:
            result = session.execute(delete(test_sets_table).where(test_sets_table.c.id == test_set_id))
            session.commit()
        return result.rowcount > 0

    def create_report(self, report: EvalReport) -> EvalReport:
        with self._sessionmaker() as session:
            session.execute(insert(eval_runs_table).values(**_report_record(report)))
            session.commit()
        return report

    def update_report(self, report: EvalReport) -> EvalReport:
        with self._sessionmaker() as session:
            session.execute(update(eval_runs_table).where(eval_runs_table.c.id == report.id).values(**_report_record(report)))
            session.commit()
        return report

    def list_reports(self) -> list[dict[str, Any]]:
        with self._sessionmaker() as session:
            rows = session.execute(select(eval_runs_table).order_by(eval_runs_table.c.created_at.desc())).mappings().all()
        return [_report_from_row(dict(row)).model_dump() for row in rows]

    def get_report(self, report_id: str) -> EvalReport | None:
        with self._sessionmaker() as session:
            row = session.execute(select(eval_runs_table).where(eval_runs_table.c.id == report_id)).mappings().first()
        return _report_from_row(dict(row)) if row else None

    def delete_report(self, report_id: str) -> bool:
        with self._sessionmaker() as session:
            result = session.execute(delete(eval_runs_table).where(eval_runs_table.c.id == report_id))
            session.commit()
        return result.rowcount > 0


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _public_test_set(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row.get("description", ""),
        "sheet_names": row.get("sheet_names") or [],
        "file_name": row.get("file_name", ""),
        "count": row.get("count", 0),
        "created_at": row.get("created_at", ""),
    }


def _report_record(report: EvalReport) -> dict[str, Any]:
    data = report.model_dump()
    data["metrics"] = report.metrics.model_dump()
    data["details"] = [item.model_dump() for item in report.details]
    return data


def _report_from_row(row: dict[str, Any]) -> EvalReport:
    return EvalReport(
        id=row["id"],
        kb_id=row["kb_id"],
        kb_name=row.get("kb_name") or "",
        test_set_id=row["test_set_id"],
        test_set_name=row.get("test_set_name") or "",
        strategy=row["strategy"],
        top_k=row["top_k"],
        status=row["status"],
        metrics=row.get("metrics") or {},
        details=row.get("details") or [],
        error_message=row.get("error_message") or "",
        progress_current=row.get("progress_current") or 0,
        progress_total=row.get("progress_total") or 0,
        created_at=row.get("created_at") or "",
        finished_at=row.get("finished_at") or "",
    )
