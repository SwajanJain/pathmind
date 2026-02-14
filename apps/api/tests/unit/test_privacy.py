from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pathmind_api.database import Base
from pathmind_api.models import ApiEventLog
from pathmind_api.privacy import anonymize_ip
from pathmind_api.repositories import purge_old_api_logs


def test_anonymize_ip_masks_ipv4_and_ipv6():
    assert anonymize_ip("192.168.1.123") == "192.168.1.0"
    assert anonymize_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:0db8:85a3:0000:0000:0000:0000:0000"


def test_purge_old_api_logs_removes_entries_older_than_retention():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    session = Session()

    old_event = ApiEventLog(source="analysis", status="stored", timestamp=datetime.now(timezone.utc) - timedelta(days=120))
    recent_event = ApiEventLog(source="analysis", status="stored", timestamp=datetime.now(timezone.utc) - timedelta(days=1))
    session.add(old_event)
    session.add(recent_event)
    session.commit()

    deleted = purge_old_api_logs(session, retention_days=90)
    assert deleted == 1

    remaining = session.query(ApiEventLog).all()
    assert len(remaining) == 1
