from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from ...models import Team, User

def _admin_teams(db: Session) -> list[Team]:
    """Every active team whose user is an administrator."""
    return list(
        db.scalars(
            select(Team)
            .join(User, Team.user_id == User.id)
            .where(
                User.is_admin.is_(True),
                User.is_active.is_(True),
                Team.is_active.is_(True),
            )
            .order_by(Team.name)
        ).all()
    )


def _usable_admin_users(db: Session, exclude: User | None = None) -> list[User]:
    """Administrator users that can still sign in: active, and covering an active team."""
    users = db.scalars(
        select(User)
        .where(User.is_admin.is_(True), User.is_active.is_(True))
        .options(selectinload(User.teams))
    ).all()
    return [
        user
        for user in users
        if user.id != (exclude.id if exclude else None)
        and any(team.is_active for team in user.teams)
    ]
