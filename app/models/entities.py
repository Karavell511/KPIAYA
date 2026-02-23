import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserStatus(str, enum.Enum):
    active = "active"
    banned = "banned"


class KPIStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    disputed = "disputed"
    approved = "approved"
    archived = "archived"


class DisputeStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"
    rejected = "rejected"


class ShareScope(str, enum.Enum):
    single_kpi = "single_kpi"
    employee_all = "employee_all"
    month_all = "month_all"


class SharePermission(str, enum.Enum):
    view = "view"
    view_download = "view_download"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    whitelist_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roles: Mapped[list["Role"]] = relationship("Role", secondary="user_roles", back_populates="users")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255))
    immutable: Mapped[bool] = mapped_column(Boolean, default=False)

    permissions: Mapped[list["Permission"]] = relationship("Permission", secondary="role_permissions", back_populates="roles")
    users: Mapped[list[User]] = relationship("User", secondary="user_roles", back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(String(255))

    roles: Mapped[list[Role]] = relationship("Role", secondary="role_permissions", back_populates="permissions")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))


class KPITemplate(Base):
    __tablename__ = "kpi_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    max_total_amount: Mapped[float] = mapped_column(Numeric(14, 2))
    formula_config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    metrics: Mapped[list["KPITemplateMetric"]] = relationship("KPITemplateMetric", back_populates="template", cascade="all, delete-orphan")


class KPITemplateMetric(Base):
    __tablename__ = "kpi_template_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("kpi_templates.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    weight_percent: Mapped[float] = mapped_column(Numeric(5, 2))
    plan_value: Mapped[float] = mapped_column(Numeric(14, 4))
    allow_overtime: Mapped[bool] = mapped_column(Boolean, default=False)
    formula: Mapped[str] = mapped_column(Text)

    template: Mapped[KPITemplate] = relationship("KPITemplate", back_populates="metrics")


class KPIInstance(Base):
    __tablename__ = "kpi_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("kpi_templates.id"))
    month: Mapped[str] = mapped_column(String(7), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    overtime_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[KPIStatus] = mapped_column(Enum(KPIStatus), default=KPIStatus.draft)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template: Mapped[KPITemplate] = relationship("KPITemplate")
    metrics: Mapped[list["KPIInstanceMetric"]] = relationship("KPIInstanceMetric", back_populates="instance", cascade="all, delete-orphan")


class KPIInstanceMetric(Base):
    __tablename__ = "kpi_instance_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("kpi_instances.id", ondelete="CASCADE"))
    template_metric_id: Mapped[int] = mapped_column(ForeignKey("kpi_template_metrics.id"))
    fact_value: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    metric_result: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    overtime_result: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    instance: Mapped[KPIInstance] = relationship("KPIInstance", back_populates="metrics")


class KPIDispute(Base):
    __tablename__ = "kpi_disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("kpi_instances.id"))
    metric_id: Mapped[int | None] = mapped_column(ForeignKey("kpi_instance_metrics.id"), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text)
    status: Mapped[DisputeStatus] = mapped_column(Enum(DisputeStatus), default=DisputeStatus.open)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KPIHistory(Base):
    __tablename__ = "kpi_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KPIShareLink(Base):
    __tablename__ = "kpi_share_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, index=True)
    scope: Mapped[ShareScope] = mapped_column(Enum(ShareScope))
    permission: Mapped[SharePermission] = mapped_column(Enum(SharePermission))
    kpi_instance_id: Mapped[int | None] = mapped_column(ForeignKey("kpi_instances.id"), nullable=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="telegram")
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
