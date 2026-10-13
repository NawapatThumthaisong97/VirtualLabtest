from fastapi import Depends, Request
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.configs.db import get_db
from app.exceptions.domain import (
    ForbiddenError,
    ValidationError as DomainValidationError,
)
from app.middlewares.auth import get_current_user
from app.models.user import User
from app.schemas.rbac_schema import PermissionContext
from app.services.rbac_service import RBACService, ResourceContextPolicy


def verify_permission(
    permission_code: str,
    context_policy: ResourceContextPolicy | None = None,
    allow_collection: bool = False,
):
    permission_context = PermissionContext.model_validate(
        {"permission_code": permission_code}
    )

    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        rbac_service = RBACService()
        is_global_access = rbac_service.has_global_permission(
            db, current_user.id, permission_code
        )
        if not is_global_access and not rbac_service.has_permission(
            db, current_user.id, permission_code
        ):
            raise ForbiddenError("ไม่มีสิทธิ์ดำเนินการนี้")

        resource_domain, permission_name, scope = permission_context.parts
        action = permission_name.split(":", maxsplit=1)[0]
        is_context_required = (
            scope in {"self", "assigned", "course"}
            and not (scope == "self" and action == "create")
            and not allow_collection
        )
        if is_context_required and not is_global_access:
            if scope == "course":
                course_id_value = request.path_params.get("course_id")
                resource_keys = (
                    ("cluster_name", "cluster_id", "resource_id")
                    if resource_domain == "clusters"
                    else ("repository", "bucket_name", "resource_id", "course_id")
                )
                resource_id = next(
                    (request.path_params[key] for key in resource_keys if key in request.path_params),
                    "",
                )
            elif resource_domain == "storage":
                course_id_value = None
                resource_keys = ("repository", "bucket_name", "resource_id")
                resource_id = next(
                    (request.path_params[key] for key in resource_keys if key in request.path_params),
                    None,
                )
            else:
                course_id_value = None
                resource_keys = ("session_id", "cluster_name", "cluster_id", "resource_id")
                resource_id = next(
                    (request.path_params[key] for key in resource_keys if key in request.path_params),
                    None,
                )
            if scope == "course" and action == "create":
                resource_id = "course-create"
            if resource_id is not None:
                try:
                    request_context = PermissionContext.model_validate(
                        {
                            "permission_code": permission_code,
                            "resource_id": str(resource_id),
                        }
                    )
                except PydanticValidationError as error:
                    raise DomainValidationError("resource context ไม่ถูกต้อง") from error
                resource_id = request_context.resource_id
            try:
                course_id = UUID(str(course_id_value)) if course_id_value else None
            except ValueError as error:
                raise DomainValidationError("course_id ไม่ถูกต้อง") from error
            if (
                resource_id is None
                or context_policy is None
                or not context_policy.allows(
                    db,
                    current_user,
                    resource_domain,
                    scope,
                    str(resource_id),
                    course_id=course_id,
                    action=action,
                )
            ):
                raise ForbiddenError("ไม่สามารถยืนยันสิทธิ์กับ resource นี้ได้")

        return current_user

    return dependency