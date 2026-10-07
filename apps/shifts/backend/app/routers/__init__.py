from fastapi import APIRouter

from .auth import router as auth_router
from .account import router as account_router
from .calendar import router as calendar_router
from .exports import router as exports_router
from .dashboard import router as dashboard_router
from .swaps import router as swaps_router
from .admin.teams import router as admin_teams_router
from .admin.users import router as admin_users_router
from .admin.schedules import router as admin_schedules_router
from .admin.assignments import router as admin_assignments_router
from .admin.notifications import router as admin_notifications_router

router = APIRouter()
for domain_router in (
    auth_router,
    account_router,
    calendar_router,
    exports_router,
    dashboard_router,
    swaps_router,
    admin_teams_router,
    admin_users_router,
    admin_schedules_router,
    admin_assignments_router,
    admin_notifications_router,
):
    router.include_router(domain_router)
