from __future__ import annotations

from pathlib import Path
from datetime import UTC, datetime, timedelta

import orjson
from sqlalchemy import Boolean, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from models.config import ConfigStatus, ProxyConfig
from models.repository import RepositoryDiscoveryResult


class Base(DeclarativeBase):
    pass


class ConfigRow(Base):
    __tablename__ = "configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    protocol: Mapped[str] = mapped_column(String, index=True)
    raw: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    host: Mapped[str] = mapped_column(String)
    port: Mapped[int] = mapped_column(Integer)
    country: Mapped[str] = mapped_column(String, default="Unknown")
    isp: Mapped[str] = mapped_column(String, default="Unknown")
    ping_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connection_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    handshake_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default=ConfigStatus.UNKNOWN.value)
    status_detail: Mapped[str] = mapped_column(String, default="")
    last_check_at: Mapped[str] = mapped_column(String, default="")
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, default=0)


class RepositoryRow(Base):
    __tablename__ = "repositories"

    repository_url: Mapped[str] = mapped_column(String, primary_key=True)
    repository_name: Mapped[str] = mapped_column(String, index=True)
    owner: Mapped[str] = mapped_column(String, index=True)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    last_update: Mapped[str] = mapped_column(String, index=True)
    language: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    raw_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    original_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    protocols_json: Mapped[str] = mapped_column(Text, default="[]")
    subscription_files_count: Mapped[int] = mapped_column(Integer, default=0)
    config_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_configs: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)


class Database:
    def __init__(self, root: Path) -> None:
        db_path = root / "cache" / "luckasapp.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        required = {
            "connection_time_ms": "INTEGER",
            "handshake_time_ms": "INTEGER",
            "response_time_ms": "INTEGER",
            "status_detail": "VARCHAR DEFAULT ''",
            "last_check_at": "VARCHAR DEFAULT ''",
            "success_count": "INTEGER DEFAULT 0",
            "failure_count": "INTEGER DEFAULT 0",
        }
        with self.engine.begin() as connection:
            existing = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(configs)").fetchall()
            }
            for column, definition in required.items():
                if column not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE configs ADD COLUMN {column} {definition}")

    def upsert_configs(self, configs: list[ProxyConfig]) -> int:
        count = 0
        with Session(self.engine) as session:
            for config in configs:
                row = session.get(ConfigRow, config.id)
                if row is None:
                    row = ConfigRow(id=config.id, raw=config.raw)
                    session.add(row)
                    count += 1
                row.protocol = config.protocol
                row.name = config.name
                row.host = config.host
                row.port = config.port
                row.country = config.country
                row.isp = config.isp
                row.ping_ms = config.ping_ms
                row.connection_time_ms = config.connection_time_ms
                row.handshake_time_ms = config.handshake_time_ms
                row.response_time_ms = config.response_time_ms
                row.status = config.status.value
                row.status_detail = config.status_detail
                row.last_check_at = config.last_check_at
                row.success_count = config.success_count
                row.failure_count = config.failure_count
                row.favorite = bool(row.favorite or config.favorite)
                row.score = int(config.score)
            session.commit()
        return count

    def list_configs(self, limit: int | None = None) -> list[ProxyConfig]:
        with Session(self.engine) as session:
            statement = select(ConfigRow).order_by(ConfigRow.score.desc(), ConfigRow.name.asc())
            if limit is not None:
                statement = statement.limit(limit)
            rows = session.scalars(statement).all()
            return [
                ProxyConfig(
                    id=row.id,
                    protocol=row.protocol,
                    raw=row.raw,
                    name=row.name,
                    host=row.host,
                    port=row.port,
                    country=row.country,
                    isp=row.isp,
                    ping_ms=row.ping_ms,
                    connection_time_ms=row.connection_time_ms,
                    handshake_time_ms=row.handshake_time_ms,
                    response_time_ms=row.response_time_ms,
                    status=ConfigStatus(row.status),
                    status_detail=row.status_detail or "",
                    last_check_at=row.last_check_at or "",
                    success_count=row.success_count or 0,
                    failure_count=row.failure_count or 0,
                    favorite=row.favorite,
                    score=float(row.score),
                )
                for row in rows
            ]

    def get_config(self, config_id: str) -> ProxyConfig | None:
        with Session(self.engine) as session:
            row = session.get(ConfigRow, config_id)
            if row is None:
                return None
            return ProxyConfig(
                id=row.id,
                protocol=row.protocol,
                raw=row.raw,
                name=row.name,
                host=row.host,
                port=row.port,
                country=row.country,
                isp=row.isp,
                ping_ms=row.ping_ms,
                connection_time_ms=row.connection_time_ms,
                handshake_time_ms=row.handshake_time_ms,
                response_time_ms=row.response_time_ms,
                status=ConfigStatus(row.status),
                status_detail=row.status_detail or "",
                last_check_at=row.last_check_at or "",
                success_count=row.success_count or 0,
                failure_count=row.failure_count or 0,
                favorite=row.favorite,
                score=float(row.score),
            )

    def config_stats(self) -> dict:
        with Session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(ConfigRow)) or 0
            testing = session.scalar(
                select(func.count()).select_from(ConfigRow).where(ConfigRow.status == ConfigStatus.TESTING.value)
            ) or 0
            ready_statuses = [
                ConfigStatus.HEALTHY.value,
                ConfigStatus.WORKING.value,
                ConfigStatus.SLOW.value,
                ConfigStatus.ONLINE.value,
            ]
            failed_statuses = [
                ConfigStatus.OFFLINE.value,
                ConfigStatus.TIMEOUT.value,
                ConfigStatus.INVALID.value,
                ConfigStatus.UNSTABLE.value,
            ]
            ready = session.scalar(
                select(func.count()).select_from(ConfigRow).where(ConfigRow.status.in_(ready_statuses))
            ) or 0
            failed = session.scalar(
                select(func.count())
                .select_from(ConfigRow)
                .where(ConfigRow.status.in_(failed_statuses))
            ) or 0
            best_ping = session.scalar(
                select(func.min(ConfigRow.ping_ms)).where(ConfigRow.ping_ms.is_not(None))
            ) or 0
            average_ping = session.scalar(
                select(func.avg(ConfigRow.ping_ms)).where(ConfigRow.ping_ms.is_not(None))
            ) or 0
            best_node = session.scalar(
                select(ConfigRow.name)
                .where(ConfigRow.status.in_(ready_statuses), ConfigRow.ping_ms.is_not(None))
                .order_by(ConfigRow.ping_ms.asc())
                .limit(1)
            ) or ""
            return {
                "total": total,
                "online": ready,
                "ready": ready,
                "testing": testing,
                "offline": failed,
                "failed": failed,
                "bestPing": best_ping,
                "averagePing": int(average_ping),
                "bestNode": best_node,
                "speed": "Ready",
            }

    def delete_config(self, config_id: str) -> None:
        with Session(self.engine) as session:
            row = session.get(ConfigRow, config_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def set_favorite(self, config_id: str, favorite: bool) -> None:
        with Session(self.engine) as session:
            row = session.get(ConfigRow, config_id)
            if row is not None:
                row.favorite = favorite
                session.commit()

    def delete_failed_configs(self, min_failures: int = 3, max_age_hours: int = 24) -> int:
        failed_statuses = [
            ConfigStatus.OFFLINE.value,
            ConfigStatus.TIMEOUT.value,
            ConfigStatus.INVALID.value,
        ]
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ConfigRow).where(
                    ConfigRow.status.in_(failed_statuses),
                    ConfigRow.failure_count >= min_failures,
                    ConfigRow.favorite.is_(False),
                    ConfigRow.last_check_at <= cutoff,
                )
            ).all()
            count = len(rows)
            for row in rows:
                session.delete(row)
            session.commit()
        return count

    def mark_remote_removed(self, config_ids: set[str]) -> int:
        if not config_ids:
            return 0
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with Session(self.engine) as session:
            rows = session.scalars(select(ConfigRow).where(ConfigRow.id.in_(config_ids))).all()
            for row in rows:
                if row.favorite:
                    row.status = ConfigStatus.OFFLINE.value
                    row.status_detail = "Removed from GitHub distribution"
                    row.ping_ms = None
                    row.connection_time_ms = None
                    row.handshake_time_ms = None
                    row.response_time_ms = None
                    row.last_check_at = now
                    row.failure_count = (row.failure_count or 0) + 1
                    row.score = 0
                else:
                    session.delete(row)
            session.commit()
            return len(rows)

    def purge_remote_removed(self) -> int:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ConfigRow).where(
                    ConfigRow.status_detail == "Removed from GitHub distribution",
                    ConfigRow.favorite.is_(False),
                )
            ).all()
            count = len(rows)
            for row in rows:
                session.delete(row)
            session.commit()
            return count

    def prune_to_processed(self, active_ids: set[str]) -> int:
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with Session(self.engine) as session:
            rows = session.scalars(select(ConfigRow).where(~ConfigRow.id.in_(active_ids))).all()
            count = len(rows)
            for row in rows:
                if row.favorite:
                    row.status = ConfigStatus.OFFLINE.value
                    row.status_detail = "Not present in processed GitHub server list"
                    row.ping_ms = None
                    row.connection_time_ms = None
                    row.handshake_time_ms = None
                    row.response_time_ms = None
                    row.last_check_at = now
                    row.failure_count = (row.failure_count or 0) + 1
                    row.score = 0
                else:
                    session.delete(row)
            session.commit()
            return count

    def count_by_status(self) -> dict[str, int]:
        failed = [s.value for s in (ConfigStatus.OFFLINE, ConfigStatus.TIMEOUT, ConfigStatus.INVALID, ConfigStatus.UNSTABLE)]
        ready = [s.value for s in (ConfigStatus.HEALTHY, ConfigStatus.WORKING, ConfigStatus.SLOW, ConfigStatus.ONLINE)]
        with Session(self.engine) as session:
            return {
                "total": session.scalar(select(func.count()).select_from(ConfigRow)) or 0,
                "ready": session.scalar(
                    select(func.count()).select_from(ConfigRow).where(ConfigRow.status.in_(ready))
                ) or 0,
                "failed": session.scalar(
                    select(func.count()).select_from(ConfigRow).where(ConfigRow.status.in_(failed))
                ) or 0,
            }

    def upsert_repositories(self, repositories: list[RepositoryDiscoveryResult]) -> int:
        count = 0
        with Session(self.engine) as session:
            for repository in repositories:
                row = session.get(RepositoryRow, repository.repository_url)
                if row is None:
                    row = RepositoryRow(repository_url=repository.repository_url)
                    session.add(row)
                    count += 1
                row.repository_name = repository.repository_name
                row.owner = repository.owner
                row.stars = repository.stars
                row.forks = repository.forks
                row.last_update = repository.last_update
                row.language = repository.language
                row.description = repository.description
                row.raw_urls_json = orjson.dumps(repository.raw_urls).decode("utf-8")
                row.original_urls_json = orjson.dumps(repository.original_urls).decode("utf-8")
                row.protocols_json = orjson.dumps(repository.protocols).decode("utf-8")
                row.subscription_files_count = repository.subscription_files_count
                row.config_count = repository.config_count
                row.valid_configs = repository.valid_configs
                row.score = repository.score
            session.commit()
        return count

    def list_repositories(self) -> list[RepositoryDiscoveryResult]:
        with Session(self.engine) as session:
            rows = session.scalars(select(RepositoryRow).order_by(RepositoryRow.score.desc())).all()
            return [
                RepositoryDiscoveryResult(
                    repository_name=row.repository_name,
                    owner=row.owner,
                    stars=row.stars,
                    forks=row.forks,
                    last_update=row.last_update,
                    language=row.language,
                    description=row.description,
                    repository_url=row.repository_url,
                    original_urls=orjson.loads(row.original_urls_json),
                    raw_urls=orjson.loads(row.raw_urls_json),
                    subscription_files_count=row.subscription_files_count,
                    protocols=orjson.loads(row.protocols_json),
                    config_count=row.config_count,
                    valid_configs=row.valid_configs,
                    score=row.score,
                )
                for row in rows
            ]
