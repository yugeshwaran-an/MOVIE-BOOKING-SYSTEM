"""
Automated Test Suite for Movie Ticket Booking System
Covers test cases T1 through T12 mandated by the Software Engineering assessment.
"""
import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.user import User
from models.resource import Resource
from models.schedule import Schedule
from models.reservation import Reservation
from models.reservation_item import ReservationItem
from models.booking_status_history import BookingStatusHistory
from services.availability_service import AvailabilityService
from app import create_app
import database_setup


@pytest.fixture
def test_env():
    """Setup an isolated temporary SQLite database and seeded tables."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    test_db_url = f"sqlite:///{db_path}"

    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Seed required demonstration data
    session = TestingSessionLocal()
    users = [
        User(id="user1", username="user1", name="Alice", role="USER", status="ACTIVE"),
        User(id="user2", username="user2", name="Bob", role="USER", status="ACTIVE"),
        User(id="admin", username="admin", name="Administrator", role="ADMINISTRATOR", status="ACTIVE")
    ]
    session.add_all(users)

    resources = [
        Resource(id="R101", name="Weathering With You", rate=499.0, availability=10, status="ACTIVE"),
        Resource(id="R102", name="Spider-Man: Brand New Day", rate=799.0, availability=5, status="ACTIVE"),
        Resource(id="R103", name="Naruto", rate=199.0, availability=20, status="ACTIVE"),
        Resource(id="R104", name="One Piece", rate=1299.0, availability=0, status="ACTIVE"),
        Resource(id="R105", name="BLEACH: Thousand-Year Blood War - The Calamity", rate=1000.0, availability=3, status="ACTIVE"),
    ]
    session.add_all(resources)
    session.commit()
    session.close()

    # Monkeypatch app and database_setup engines
    orig_engine = database_setup.engine
    orig_session = database_setup.SessionLocal
    database_setup.engine = engine
    database_setup.SessionLocal = TestingSessionLocal

    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret'
    client = app.test_client()

    yield {
        'engine': engine,
        'session_factory': TestingSessionLocal,
        'app': app,
        'client': client,
        'db_path': db_path
    }

    # Teardown
    database_setup.engine = orig_engine
    database_setup.SessionLocal = orig_session
    engine.dispose()
    os.close(db_fd)
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass


def login_client(client, username):
    """Helper to simulate login session."""
    with client.session_transaction() as sess:
        sess['user_id'] = username
        sess['username'] = username
        sess['name'] = "Test User" if username != 'admin' else "Administrator"
        sess['role'] = 'ADMINISTRATOR' if username == 'admin' else 'USER'


# --------------------------------------------------------------------------
# T1: Select same resource twice
# --------------------------------------------------------------------------
def test_t1_select_same_resource_twice(test_env):
    """
    T1: Selecting/viewing the same resource twice does not create duplicate
    or prematurely reserved records.
    """
    client = test_env['client']
    login_client(client, 'user1')

    # View booking page for R101 first time
    resp1 = client.get('/booking/R101')
    assert resp1.status_code == 200

    # View booking page for R101 second time
    resp2 = client.get('/booking/R101')
    assert resp2.status_code == 200

    # Verify no reservation record created and availability unchanged (still 10)
    session = test_env['session_factory']()
    res_count = session.query(Reservation).count()
    r101 = session.query(Resource).filter_by(id='R101').first()
    assert res_count == 0
    assert r101.availability == 10
    session.close()


# --------------------------------------------------------------------------
# T2: Try quantities: 0, 1, 5, 6, 1.5
# --------------------------------------------------------------------------
def test_t2_quantity_validation(test_env):
    """
    T2: BR1 - Accept only integer values 1 to 5.
    Reject 0, negative numbers, values above 5, decimal values (1.5), non-numeric.
    """
    # 0 -> Reject
    valid_0, qty_0, _ = AvailabilityService.validate_quantity(0)
    assert not valid_0

    # 1 -> Accept (Boundary)
    valid_1, qty_1, _ = AvailabilityService.validate_quantity(1)
    assert valid_1 and qty_1 == 1

    # 5 -> Accept (Boundary)
    valid_5, qty_5, _ = AvailabilityService.validate_quantity(5)
    assert valid_5 and qty_5 == 5

    # 6 -> Reject (Above upper bound)
    valid_6, qty_6, _ = AvailabilityService.validate_quantity(6)
    assert not valid_6

    # 1.5 -> Reject (Decimal)
    valid_dec, _, _ = AvailabilityService.validate_quantity(1.5)
    assert not valid_dec

    valid_str_dec, _, _ = AvailabilityService.validate_quantity("1.5")
    assert not valid_str_dec

    valid_neg, _, _ = AvailabilityService.validate_quantity(-1)
    assert not valid_neg

    valid_non_num, _, _ = AvailabilityService.validate_quantity("abc")
    assert not valid_non_num


# --------------------------------------------------------------------------
# T3: Try unavailable resource R104
# --------------------------------------------------------------------------
def test_t3_unavailable_resource_r104(test_env):
    """
    T3: BR2 - Try booking unavailable resource R104 (initial availability: 0).
    Expected: Rejected and system state unchanged.
    """
    client = test_env['client']
    login_client(client, 'user1')

    post_data = {
        'resource_id': 'R104',
        'quantity': '1',
        'name': 'Alice Smith',
        'phone': '9876543210',
        'booking_date': '2026-10-11',
        'reference_info': 'ID-12345'
    }
    resp = client.post('/booking/confirm', data=post_data)
    assert resp.status_code == 400
    assert b"This show is currently unavailable" in resp.data

    session = test_env['session_factory']()
    res_count = session.query(Reservation).count()
    r104 = session.query(Resource).filter_by(id='R104').first()
    assert res_count == 0
    assert r104.availability == 0
    session.close()


# --------------------------------------------------------------------------
# T4: Test amounts: Rs.999, Rs.1000, Rs.1001
# --------------------------------------------------------------------------
def test_t4_booking_charge_boundaries(test_env):
    """
    T4: BR4 - Booking charge boundary tests:
    IF base_total < 1000: booking_charge = 50
    IF base_total >= 1000: booking_charge = 0
    """
    # Boundary 1: Rs. 999 (< 1000)
    base_999, charge_999, total_999 = AvailabilityService.calculate_pricing(999.0, 1)
    assert base_999 == 999.0
    assert charge_999 == 50.0
    assert total_999 == 1049.0

    # Boundary 2: Rs. 1000 (== 1000)
    base_1000, charge_1000, total_1000 = AvailabilityService.calculate_pricing(1000.0, 1)
    assert base_1000 == 1000.0
    assert charge_1000 == 0.0
    assert total_1000 == 1000.0

    # Boundary 3: Rs. 1001 (> 1000)
    base_1001, charge_1001, total_1001 = AvailabilityService.calculate_pricing(1001.0, 1)
    assert base_1001 == 1001.0
    assert charge_1001 == 0.0
    assert total_1001 == 1001.0


# --------------------------------------------------------------------------
# T5: Complete one valid reservation
# --------------------------------------------------------------------------
def test_t5_complete_valid_reservation(test_env):
    """
    T5: BR7 - One valid reservation creates 1 CONFIRMED reservation,
    saves item snapshot, reduces availability, and records history.
    """
    client = test_env['client']
    login_client(client, 'user1')

    post_data = {
        'resource_id': 'R101',  # Rate 499, Initial availability 10
        'quantity': '2',
        'name': 'Alice Wonderland',
        'phone': '9876543210',
        'booking_date': '2026-10-10',
        'reference_info': 'ID-ALICE-01'
    }
    resp = client.post('/booking/confirm', data=post_data, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Reservation Confirmed" in resp.data

    session = test_env['session_factory']()
    reservations = session.query(Reservation).all()
    assert len(reservations) == 1
    res = reservations[0]

    assert res.user_id == 'user1'
    assert res.status == 'CONFIRMED'
    assert res.customer_name == 'Alice Wonderland'
    assert res.customer_phone == '9876543210'

    # Check Reservation Item
    assert len(res.items) == 1
    item = res.items[0]
    assert item.resource_id == 'R101'
    assert item.quantity == 2
    assert item.rate_snapshot == 499.0
    assert item.base_amount == 998.0
    assert item.booking_charge == 50.0  # < 1000
    assert item.grand_total == 1048.0
    assert res.total_amount == 1048.0

    # Check reduced availability
    r101 = session.query(Resource).filter_by(id='R101').first()
    assert r101.availability == 8  # 10 - 2

    # Check status history
    assert len(res.status_history) == 1
    history = res.status_history[0]
    assert history.old_status is None
    assert history.new_status == 'CONFIRMED'
    assert history.actor_id == 'user1'

    session.close()


# --------------------------------------------------------------------------
# T6: Confirm with invalid/missing details
# --------------------------------------------------------------------------
def test_t6_confirm_with_invalid_details(test_env):
    """
    T6: BR5, BR6 - Reject when details are blank or invalid.
    Ensure no reservation is created and capacity is not reduced.
    """
    client = test_env['client']
    login_client(client, 'user1')

    # Test 1: Blank Name
    resp1 = client.post('/booking/confirm', data={
        'resource_id': 'R101',
        'quantity': '1',
        'name': '   ',
        'phone': '9876543210',
        'booking_date': '2026-10-10',
        'reference_info': 'REF-1'
    })
    assert resp1.status_code == 400
    assert b"Name cannot be blank" in resp1.data

    # Test 2: Invalid Phone (9 digits)
    resp2 = client.post('/booking/confirm', data={
        'resource_id': 'R101',
        'quantity': '1',
        'name': 'Alice',
        'phone': '123456789',  # 9 digits
        'booking_date': '2026-10-10',
        'reference_info': 'REF-1'
    })
    assert resp2.status_code == 400
    assert b"Phone number must contain exactly 10 digits" in resp2.data

    # Test 3: Invalid Phone (11 digits)
    resp3 = client.post('/booking/confirm', data={
        'resource_id': 'R101',
        'quantity': '1',
        'name': 'Alice',
        'phone': '12345678901',  # 11 digits
        'booking_date': '2026-10-10',
        'reference_info': 'REF-1'
    })
    assert resp3.status_code == 400
    assert b"Phone number must contain exactly 10 digits" in resp3.data

    # Test 4: Missing Date
    resp4 = client.post('/booking/confirm', data={
        'resource_id': 'R101',
        'quantity': '1',
        'name': 'Alice',
        'phone': '9876543210',
        'booking_date': '',
        'reference_info': 'REF-1'
    })
    assert resp4.status_code == 400
    assert b"Booking details are invalid" in resp4.data

    # Verify no database change
    session = test_env['session_factory']()
    assert session.query(Reservation).count() == 0
    r101 = session.query(Resource).filter_by(id='R101').first()
    assert r101.availability == 10
    session.close()


# --------------------------------------------------------------------------
# T7: Change availability before confirmation
# --------------------------------------------------------------------------
def test_t7_change_availability_before_confirmation(test_env):
    """
    T7: BR2, BR6 - If availability drops below requested quantity before
    confirmation, rejection occurs and atomic rollback happens.
    """
    client = test_env['client']
    login_client(client, 'user1')

    # Simulate another booking taking seats for R102 (initial 5 seats)
    session = test_env['session_factory']()
    r102 = session.query(Resource).filter_by(id='R102').first()
    r102.availability = 1  # Reduced to 1
    session.commit()
    session.close()

    # User tries to book 3 seats
    resp = client.post('/booking/confirm', data={
        'resource_id': 'R102',
        'quantity': '3',
        'name': 'Alice',
        'phone': '9876543210',
        'booking_date': '2026-10-10',
        'reference_info': 'REF-1'
    })
    assert resp.status_code == 400
    assert b"Requested quantity is not available" in resp.data

    session = test_env['session_factory']()
    assert session.query(Reservation).count() == 0
    r102 = session.query(Resource).filter_by(id='R102').first()
    assert r102.availability == 1  # Unchanged
    session.close()


# --------------------------------------------------------------------------
# T8: User attempts to access another user's booking/status
# --------------------------------------------------------------------------
def test_t8_unauthorized_user_access(test_env):
    """
    T8: BR10 - User 2 cannot view or cancel User 1's booking.
    """
    client = test_env['client']

    # User 1 books a show
    login_client(client, 'user1')
    client.post('/booking/confirm', data={
        'resource_id': 'R101',
        'quantity': '1',
        'name': 'Alice',
        'phone': '9876543210',
        'booking_date': '2026-10-10',
        'reference_info': 'REF-1'
    })

    session = test_env['session_factory']()
    bkg = session.query(Reservation).filter_by(user_id='user1').first()
    booking_id = bkg.id
    session.close()

    # Switch session to User 2
    login_client(client, 'user2')

    # User 2 attempts to view details of User 1's booking
    resp_view = client.get(f'/booking/{booking_id}/details')
    assert resp_view.status_code == 403
    assert b"You are not authorized to access this booking" in resp_view.data

    # User 2 attempts to cancel User 1's booking
    resp_cancel = client.post(f'/booking/{booking_id}/cancel')
    assert resp_cancel.status_code == 403

    # Check booking status remains CONFIRMED
    session = test_env['session_factory']()
    res = session.query(Reservation).filter_by(id=booking_id).first()
    assert res.status == 'CONFIRMED'
    session.close()


# --------------------------------------------------------------------------
# T9: Administrator advances valid stages and attempts invalid skipping
# --------------------------------------------------------------------------
def test_t9_admin_status_transitions_and_skipping(test_env):
    """
    T9: BR8 - Administrator can only advance status to valid next stage.
    CONFIRMED -> CHECKED_IN -> COMPLETED
    Direct CONFIRMED -> COMPLETED must be rejected.
    """
    client = test_env['client']

    # User 1 creates confirmed booking
    login_client(client, 'user1')
    client.post('/booking/confirm', data={
        'resource_id': 'R103',
        'quantity': '2',
        'name': 'Alice',
        'phone': '9876543210',
        'booking_date': '2026-10-11',
        'reference_info': 'REF-1'
    })

    session = test_env['session_factory']()
    res = session.query(Reservation).first()
    booking_id = res.id
    session.close()

    # Login as Administrator
    login_client(client, 'admin')

    # Attempt INVALID transition: CONFIRMED -> COMPLETED (skipping CHECKED_IN)
    resp_invalid = client.post(f'/admin/booking/{booking_id}/status', data={'new_status': 'COMPLETED'})
    assert resp_invalid.status_code == 400
    assert b"Invalid booking status transition" in resp_invalid.data

    # Valid step 1: CONFIRMED -> CHECKED_IN
    resp_valid_1 = client.post(f'/admin/booking/{booking_id}/status', data={'new_status': 'CHECKED_IN'}, follow_redirects=True)
    assert resp_valid_1.status_code == 200

    session = test_env['session_factory']()
    res = session.query(Reservation).filter_by(id=booking_id).first()
    assert res.status == 'CHECKED_IN'
    session.close()

    # Valid step 2: CHECKED_IN -> COMPLETED
    resp_valid_2 = client.post(f'/admin/booking/{booking_id}/status', data={'new_status': 'COMPLETED'}, follow_redirects=True)
    assert resp_valid_2.status_code == 200

    session = test_env['session_factory']()
    res = session.query(Reservation).filter_by(id=booking_id).first()
    assert res.status == 'COMPLETED'
    session.close()

    # Attempt INVALID transition: COMPLETED -> CANCELLED
    resp_invalid_cancel = client.post(f'/admin/booking/{booking_id}/status', data={'new_status': 'CANCELLED'})
    assert resp_invalid_cancel.status_code == 400
    assert b"Invalid booking status transition" in resp_invalid_cancel.data


# --------------------------------------------------------------------------
# T10: Cancel eligible booking and repeat cancellation
# --------------------------------------------------------------------------
def test_t10_cancellation_and_repeat_prevention(test_env):
    """
    T10: BR8, BR9 - First cancellation succeeds and restores capacity once.
    Second cancellation is rejected and does NOT restore capacity again.
    """
    client = test_env['client']
    login_client(client, 'user1')

    # Book 2 seats of R101 (initial 10 seats -> 8 seats)
    client.post('/booking/confirm', data={
        'resource_id': 'R101',
        'quantity': '2',
        'name': 'Alice',
        'phone': '9876543210',
        'booking_date': '2026-10-10',
        'reference_info': 'REF-1'
    })

    session = test_env['session_factory']()
    bkg = session.query(Reservation).first()
    booking_id = bkg.id
    r101 = session.query(Resource).filter_by(id='R101').first()
    assert r101.availability == 8
    session.close()

    # First cancellation by owner
    resp_cancel_1 = client.post(f'/booking/{booking_id}/cancel', follow_redirects=True)
    assert resp_cancel_1.status_code == 200

    session = test_env['session_factory']()
    bkg = session.query(Reservation).filter_by(id=booking_id).first()
    r101 = session.query(Resource).filter_by(id='R101').first()
    assert bkg.status == 'CANCELLED'
    assert r101.availability == 10  # Restored exactly once (8 + 2)
    histories_count = session.query(BookingStatusHistory).filter_by(reservation_id=booking_id).count()
    assert histories_count == 2  # CONFIRMED -> CANCELLED
    session.close()

    # Second cancellation attempt
    resp_cancel_2 = client.post(f'/booking/{booking_id}/cancel')
    assert resp_cancel_2.status_code == 400
    assert b"Booking has already been cancelled" in resp_cancel_2.data

    # Verify availability is NOT restored a second time (must remain 10, not 12)
    session = test_env['session_factory']()
    r101 = session.query(Resource).filter_by(id='R101').first()
    assert r101.availability == 10
    histories_count_after = session.query(BookingStatusHistory).filter_by(reservation_id=booking_id).count()
    assert histories_count_after == 2
    session.close()


# --------------------------------------------------------------------------
# T11: Restart application after successful booking
# --------------------------------------------------------------------------
def test_t11_persistence_after_restart(test_env):
    """
    T11: FR10, Section 14 - Data persistence across app stop/restart.
    SQLite database retains bookings, items, history, and availability.
    """
    client = test_env['client']
    login_client(client, 'user1')

    # Create a booking
    client.post('/booking/confirm', data={
        'resource_id': 'R105',  # Initial 3 seats, rate 1000
        'quantity': '2',
        'name': 'Persistence Tester',
        'phone': '9876543210',
        'booking_date': '2026-10-11',
        'reference_info': 'ID-PERSIST'
    })

    # Dispose existing connection/session to simulate stopping the app
    test_env['engine'].dispose()

    # Simulate restart by creating new engine and session pointing to same DB file
    new_engine = create_engine(f"sqlite:///{test_env['db_path']}")
    NewSession = sessionmaker(bind=new_engine)
    new_session = NewSession()

    bkg = new_session.query(Reservation).filter_by(customer_name='Persistence Tester').first()
    assert bkg is not None
    assert bkg.status == 'CONFIRMED'
    assert bkg.total_amount == 2000.0

    r105 = new_session.query(Resource).filter_by(id='R105').first()
    assert r105.availability == 1  # 3 - 2

    assert len(bkg.items) == 1
    assert bkg.items[0].quantity == 2

    new_session.close()
    new_engine.dispose()


# --------------------------------------------------------------------------
# T12: Change rate after booking
# --------------------------------------------------------------------------
def test_t12_rate_snapshot_preservation(test_env):
    """
    T12: BR3 - Old booking retains original fare snapshot even if
    resource rate is changed subsequently.
    """
    client = test_env['client']
    login_client(client, 'user1')

    # Book R101 when rate is Rs. 499
    client.post('/booking/confirm', data={
        'resource_id': 'R101',
        'quantity': '1',
        'name': 'Rate Snapshot User',
        'phone': '9876543210',
        'booking_date': '2026-10-10',
        'reference_info': 'ID-SNAPSHOT'
    })

    session = test_env['session_factory']()
    bkg = session.query(Reservation).filter_by(customer_name='Rate Snapshot User').first()
    booking_id = bkg.id

    # Now simulate an administrative rate update on R101 (e.g. price increase to 899.0)
    r101 = session.query(Resource).filter_by(id='R101').first()
    r101.rate = 899.0
    session.commit()
    session.close()

    # Verify the existing reservation retains original snapshot
    session = test_env['session_factory']()
    bkg_after = session.query(Reservation).filter_by(id=booking_id).first()
    item = bkg_after.items[0]
    assert item.rate_snapshot == 499.0
    assert item.base_amount == 499.0
    assert item.booking_charge == 50.0
    assert item.grand_total == 549.0
    assert bkg_after.total_amount == 549.0

    # Current resource rate is indeed changed to 899
    r101_curr = session.query(Resource).filter_by(id='R101').first()
    assert r101_curr.rate == 899.0
    session.close()


# --------------------------------------------------------------------------
# T13: Admin creates a new movie show, toggles status, and deletes
# --------------------------------------------------------------------------
def test_t13_admin_create_and_manage_movie(test_env):
    """
    Test that an Administrator can create a new movie show, view it in the listings,
    toggle its status, and delete it.
    """
    client = test_env['client']
    login_client(client, 'admin')

    # GET movie creation form
    resp_get = client.get('/admin/movie/create')
    assert resp_get.status_code == 200
    assert b"Add New Movie Show" in resp_get.data

    # POST new movie creation
    new_movie_data = {
        'id': 'R106',
        'name': 'Demon Slayer: Infinity Castle',
        'rate': '650.0',
        'availability': '30',
        'show_date': '2026-10-15',
        'show_time': '08:00 PM',
        'category': 'IMAX 3D - Screen 5',
        'status': 'ACTIVE'
    }
    resp_post = client.post('/admin/movie/create', data=new_movie_data, follow_redirects=True)
    assert resp_post.status_code == 200
    assert b"Demon Slayer: Infinity Castle" in resp_post.data

    # Verify resource exists in DB
    session = test_env['session_factory']()
    movie = session.query(Resource).filter_by(id='R106').first()
    assert movie is not None
    assert movie.name == 'Demon Slayer: Infinity Castle'
    assert movie.rate == 650.0
    assert movie.availability == 30
    assert movie.status == 'ACTIVE'
    assert len(movie.schedules) == 1
    assert movie.schedules[0].category == 'IMAX 3D - Screen 5'
    session.close()

    # Toggle status to INACTIVE
    resp_toggle = client.post('/admin/movie/R106/toggle-status', follow_redirects=True)
    assert resp_toggle.status_code == 200
    session = test_env['session_factory']()
    movie = session.query(Resource).filter_by(id='R106').first()
    assert movie.status == 'INACTIVE'
    session.close()

    # Delete the newly created movie
    resp_delete = client.post('/admin/movie/R106/delete', follow_redirects=True)
    assert resp_delete.status_code == 200
    session = test_env['session_factory']()
    movie = session.query(Resource).filter_by(id='R106').first()
    assert movie is None
    session.close()

