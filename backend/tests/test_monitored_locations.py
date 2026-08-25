"""Tests for the user-owned monitored_locations feature."""

from app.models.monitored_location import MonitoredLocation
from app.models.user import User
from app.repositories.monitored_location_repository import (
    MonitoredLocationRepository,
)


def make_user(db_session, email="mon@example.com") -> User:
    user = User(email=email, hashed_password="x" * 60, is_verified=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestMonitoredLocationRepository:
    def test_create_and_get_enabled(self, db_session):
        repo = MonitoredLocationRepository(db_session)
        loc = repo.create(
            name="Delhi", latitude=28.61, longitude=77.21, radius=500
        )
        assert loc.id is not None
        assert loc.enabled is True  # default on

        enabled = repo.get_enabled()
        assert [l.name for l in enabled] == ["Delhi"]

    def test_disabled_locations_are_not_collected(self, db_session):
        repo = MonitoredLocationRepository(db_session)
        repo.create(name="On", latitude=1.0, longitude=2.0, enabled=True)
        repo.create(name="Off", latitude=3.0, longitude=4.0, enabled=False)

        assert [l.name for l in repo.get_enabled()] == ["On"]

    def test_locations_are_user_scoped(self, db_session):
        user_a = make_user(db_session, "a@example.com")
        user_b = make_user(db_session, "b@example.com")
        repo = MonitoredLocationRepository(db_session)
        mine = repo.create(
            name="Mine", latitude=0, longitude=0, user_id=user_a.id
        )
        theirs = repo.create(
            name="Theirs", latitude=1, longitude=1, user_id=user_b.id
        )

        names = {l.name for l in repo.get_enabled_for_user(user_a.id)}
        assert names == {"Mine"}

    def test_global_location_has_null_user(self, db_session):
        """Operator-seeded platform locations have no owner."""
        repo = MonitoredLocationRepository(db_session)
        loc = repo.create(name="Global", latitude=0, longitude=0, user_id=None)
        assert loc.user_id is None
        # Global locations appear in the schedule discovery...
        assert loc in repo.get_enabled()
        # ...but not under any single user's scope.
        assert repo.get_enabled_for_user(999) == []

    def test_as_task_args_shape(self, db_session):
        repo = MonitoredLocationRepository(db_session)
        loc = repo.create(name="X", latitude=5.5, longitude=6.6)
        args = loc.as_task_args()
        assert args == {
            "lat": 5.5,
            "lon": 6.6,
            "location_name": "X",
            "location_id": loc.id,
        }

    def test_delete_user_cascades_locations(self, db_session):
        user = make_user(db_session, "cascade@example.com")
        repo = MonitoredLocationRepository(db_session)
        repo.create(name="Doomed", latitude=0, longitude=0, user_id=user.id)
        assert len(repo.get_enabled()) == 1

        db_session.delete(user)
        db_session.commit()
        assert repo.get_enabled() == []
