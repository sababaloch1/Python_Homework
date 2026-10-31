from datetime import date
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.app.core.database import Base
from api.app.core.enums import ActivityCategory, Scope, Scope2Method, Unit, UserRole
from api.app.core.models import ActivityRecord, EmissionResult, Organization, User
from api.app.analytics.base import base_results_query


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_base_results_query_filters(db_session):
    # Setup test orgs
    org1 = Organization(name="Test Org 1", employee_count=100)
    org2 = Organization(name="Test Org 2", employee_count=50)
    db_session.add_all([org1, org2])
    db_session.commit()

    # Create ActivityRecords for org1 and org2
    act_org1_1 = ActivityRecord(
        org_id=org1.id,
        category=ActivityCategory.electricity,
        amount=Decimal("1000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    act_org1_2 = ActivityRecord(
        org_id=org1.id,
        category=ActivityCategory.natural_gas,
        amount=Decimal("500"),
        unit=Unit.kWh,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
    )
    act_org2 = ActivityRecord(
        org_id=org2.id,
        category=ActivityCategory.electricity,
        amount=Decimal("2000"),
        unit=Unit.kWh,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    db_session.add_all([act_org1_1, act_org1_2, act_org2])
    db_session.commit()

    # 1. Valid location-based result for Org 1 (SHOULD BE INCLUDED)
    r1 = EmissionResult(
        activity_id=act_org1_1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("400.00"),
        is_current=True,
    )
    # 2. Result with NULL method (e.g. Scope 1) (SHOULD BE INCLUDED)
    r2 = EmissionResult(
        activity_id=act_org1_2.id,
        scope=Scope.scope_1,
        method=None,
        kg_co2e=Decimal("100.00"),
        is_current=True,
    )
    # 3. Market-based result (MUST NOT BE ADDED TO LOCATION-BASED TOTALS)
    r3 = EmissionResult(
        activity_id=act_org1_1.id,
        scope=Scope.scope_2,
        method=Scope2Method.market_based,
        kg_co2e=Decimal("50.00"),
        is_current=True,
    )
    # 4. Result where is_current is False (MUST BE EXCLUDED)
    r4 = EmissionResult(
        activity_id=act_org1_1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("380.00"),
        is_current=False,
    )
    # 5. Result where kg_co2e is NULL (MUST BE EXCLUDED)
    r5 = EmissionResult(
        activity_id=act_org1_1.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=None,
        is_current=True,
    )
    # 6. Valid result for other org (Org 2) (MUST BE EXCLUDED)
    r6 = EmissionResult(
        activity_id=act_org2.id,
        scope=Scope.scope_2,
        method=Scope2Method.location_based,
        kg_co2e=Decimal("800.00"),
        is_current=True,
    )

    db_session.add_all([r1, r2, r3, r4, r5, r6])
    db_session.commit()

    # Run query for org1
    stmt = base_results_query(db=db_session, org_id=org1.id)
    results = db_session.execute(stmt).all()

    # Should only return r1 and r2!
    result_ids = [row[0].id for row in results]
    assert r1.id in result_ids
    assert r2.id in result_ids
    assert r3.id not in result_ids  # market_based excluded
    assert r4.id not in result_ids  # is_current False excluded
    assert r5.id not in result_ids  # NULL kg_co2e excluded
    assert r6.id not in result_ids  # other org excluded
    assert len(results) == 2

    # Test date filtering
    stmt_jan = base_results_query(db=db_session, org_id=org1.id, start=date(2026, 1, 1), end=date(2026, 1, 31))
    jan_results = db_session.execute(stmt_jan).all()
    assert len(jan_results) == 1
    assert jan_results[0][0].id == r1.id
