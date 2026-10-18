from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.rbac import Permission, Role, RolePermission, UserRoleAssignment
from app.models.user import User


PERMISSIONS = {
    "clusters:create:self": "Create a personal cluster subject to the user's restricted quota.",
    "clusters:read:self": "Read the user's own personal clusters.",
    "clusters:delete:self": "Delete the user's own personal clusters.",
    "clusters:create:course": "Create clusters for an assigned course.",
    "clusters:read:course": "Read clusters for an assigned course.",
    "clusters:update:course": "Update the lifecycle of clusters for an assigned course.",
    "clusters:delete:course": "Delete clusters for an assigned course.",
    "clusters:manage:global": "Full infrastructure cluster control.",
    "kubernetes:cluster_admin:self": "Cluster-admin inside the user's own cluster only.",
    "kubernetes:workloads:view:assigned": "Read workloads in assigned student clusters.",
    "kubernetes:workloads:exec:assigned": "Exec into workloads in assigned student clusters.",
    "kubernetes:workloads:logs:assigned": "Read logs in assigned student clusters.",
    "kubernetes:cluster_admin:global": "Global Kubernetes cluster-admin.",
    "network:tailscale:access:self": "Access the user's own node or container through Tailscale.",
    "network:tailscale:access:assigned": "Access assigned student subnets through Tailscale.",
    "network:policies:manage:global": "Manage global network policies.",
    "network:tailscale:manage:global": "Manage the Tailscale network configuration.",
    "network:egress_allowlist:manage:global": "Manage the strict egress allowlist.",
    "storage:images:pull:self": "Pull images from the user's personal registry repository.",
    "storage:images:push:self": "Push images only to the user's personal registry repository.",
    "storage:data:read_write:self": "Read and write data only in the user's personal R2 bucket.",
    "storage:images:push:course": "Push course images to the registry.",
    "storage:datasets:manage:course": "Manage R2 datasets for assigned courses.",
    "storage:r2:manage:global": "Manage all R2 buckets and datasets.",
    "storage:registry:manage:global": "Manage the global registry.",
    "storage:quotas:manage:global": "Manage global storage and compute quotas.",
    # Course Management Permissions
    "courses:read:self": "View courses you're enrolled in or teaching.",
    "courses:create:self": "Create new courses (Instructor only).",
    "courses:update:course": "Update course information for courses you teach.",
    "courses:delete:course": "Delete courses you created or teach.",
    "courses:manage:global": "Full course management access (Admin).",
    "courses:announcements:create:course": "Create announcements for courses you teach.",
    "courses:announcements:update:course": "Update announcements for courses you teach.",
    "courses:announcements:delete:course": "Delete announcements for courses you teach.",
    # Monitoring & SIEM Permissions
    "metrics:read:global": "Read cluster metrics, resource allocations, and security counters (Admin only).",
    "logs:read:global": "Read critical infrastructure logs and boundary violation logs (Admin only).",
    # Billing & Financial Reporting Permissions
    "billing:read:global": "Read aggregated billing reports and export financial statements (Admin only).",
    "billing:manage:global": "Manage and delete billing report records (Admin only).",
}

ROLE_PERMISSIONS = {
    "Student": {
        "clusters:create:self",
        "clusters:read:self",
        "clusters:delete:self",
        "kubernetes:cluster_admin:self",
        "network:tailscale:access:self",
        "storage:images:pull:self",
        "storage:images:push:self",
        "storage:data:read_write:self",
        "courses:read:self",
    },
    "Instructor": {
        "clusters:create:course",
        "clusters:read:course",
        "clusters:update:course",
        "clusters:delete:course",
        "kubernetes:workloads:view:assigned",
        "kubernetes:workloads:exec:assigned",
        "kubernetes:workloads:logs:assigned",
        "network:tailscale:access:assigned",
        "storage:images:push:course",
        "storage:datasets:manage:course",
        "courses:read:self",
        "courses:create:self",
        "courses:update:course",
        "courses:delete:course",
        "courses:announcements:create:course",
        "courses:announcements:update:course",
        "courses:announcements:delete:course",
    },
    "Admin": {
        "clusters:manage:global",
        "kubernetes:cluster_admin:global",
        "network:policies:manage:global",
        "network:tailscale:manage:global",
        "network:egress_allowlist:manage:global",
        "storage:r2:manage:global",
        "storage:registry:manage:global",
        "storage:quotas:manage:global",
        "courses:manage:global",
        "metrics:read:global",
        "logs:read:global",
        "billing:read:global",
        "billing:manage:global",
    },
}

LEGACY_ROLE_NAMES = {
    "student": "Student",
    "instructor": "Instructor",
    "admin": "Admin",
}


class RBACSeeder:
    def __init__(self, db: Session):
        self.db = db

    def seed(self) -> None:
        try:
            roles = self._upsert_roles()
            permissions = self._upsert_permissions()
            self._synchronize_role_permissions(roles, permissions)
            self._migrate_legacy_user_roles(roles)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _upsert_roles(self) -> dict[str, Role]:
        roles = {}
        descriptions = {
            "Student": "Self-service access constrained to personal resources.",
            "Instructor": "Course-scoped support and course resource management.",
            "Admin": "Global infrastructure administration.",
        }
        for role_name, permission_codes in ROLE_PERMISSIONS.items():
            role = self.db.query(Role).filter(Role.role_name == role_name).one_or_none()
            if role is None:
                role = Role(
                    role_name=role_name,
                    description=descriptions[role_name],
                    is_active=True,
                )
                self.db.add(role)
            else:
                role.description = descriptions[role_name]
            roles[role_name] = role
        self.db.flush()
        return roles

    def _upsert_permissions(self) -> dict[str, Permission]:
        permissions = {}
        for permission_code, description in PERMISSIONS.items():
            resource_domain, permission_name = permission_code.split(":", maxsplit=1)
            permission = (
                self.db.query(Permission)
                .filter(
                    Permission.resource_domain == resource_domain,
                    Permission.permission_name == permission_name,
                )
                .one_or_none()
            )
            if permission is None:
                permission = Permission(
                    resource_domain=resource_domain,
                    permission_name=permission_name,
                    description=description,
                    is_active=True,
                )
                self.db.add(permission)
            else:
                permission.description = description
            permissions[permission_code] = permission
        self.db.flush()
        return permissions

    def _synchronize_role_permissions(
        self,
        roles: dict[str, Role],
        permissions: dict[str, Permission],
    ) -> None:
        role_ids = [role.id for role in roles.values()]
        existing_mappings = (
            self.db.query(RolePermission)
            .filter(RolePermission.role_id.in_(role_ids))
            .all()
        )
        mappings_by_key = {
            (mapping.role_id, mapping.permission_id): mapping
            for mapping in existing_mappings
        }

        for role_name, permission_codes in ROLE_PERMISSIONS.items():
            role = roles[role_name]
            desired_permission_ids = {
                permissions[permission_code].id for permission_code in permission_codes
            }
            for mapping in existing_mappings:
                if (
                    mapping.role_id == role.id
                    and mapping.is_seeded
                    and mapping.permission_id not in desired_permission_ids
                    and mapping.deleted_at is None
                ):
                    mapping.deleted_at = func.now()

            for permission_id in desired_permission_ids:
                mapping = mappings_by_key.get((role.id, permission_id))
                if mapping is None:
                    mapping = RolePermission(
                        role_id=role.id,
                        permission_id=permission_id,
                        is_seeded=True,
                    )
                    self.db.add(mapping)
                    mappings_by_key[(role.id, permission_id)] = mapping
                elif mapping.is_seeded:
                    mapping.deleted_at = None

    def _migrate_legacy_user_roles(self, roles: dict[str, Role]) -> None:
        users = self.db.query(User).all()
        for user in users:
            legacy_name = getattr(user.role, "value", str(user.role)).lower()
            role_name = LEGACY_ROLE_NAMES.get(legacy_name)
            if role_name is None:
                continue
            role = roles[role_name]
            if not role.is_active or role.deleted_at is not None:
                continue
            role_id = role.id
            assignment = (
                self.db.query(UserRoleAssignment)
                .filter(
                    UserRoleAssignment.user_id == user.id,
                    UserRoleAssignment.role_id == role_id,
                )
                .one_or_none()
            )
            if assignment is None:
                self.db.add(UserRoleAssignment(user_id=user.id, role_id=role_id))
