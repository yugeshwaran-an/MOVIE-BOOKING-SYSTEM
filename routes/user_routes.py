"""
User routes handling authentication, show browsing, reservations, and cancellations.
"""
import re
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.user import User
from models.resource import Resource
from models.reservation import Reservation
from models.reservation_item import ReservationItem
from models.booking_status_history import BookingStatusHistory
from services.availability_service import AvailabilityService
from routes.helpers import get_db, login_required

user_bp = Blueprint('user_bp', __name__)


@user_bp.route('/')
def index():
    if not session.get('user_id'):
        return redirect(url_for('user_bp.login'))
    if session.get('role') == 'ADMINISTRATOR':
        return redirect(url_for('admin_bp.admin_dashboard'))
    return redirect(url_for('user_bp.dashboard'))


@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    db = get_db()
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            user = db.query(User).filter_by(username=username).first()
            if not user:
                flash("Invalid user selected.", "danger")
                return redirect(url_for('user_bp.login'))

            session.clear()
            session['user_id'] = user.id
            session['username'] = user.username
            session['name'] = user.name
            session['role'] = user.role

            flash(f"Logged in successfully as {user.name} ({user.role}).", "success")
            if user.is_admin():
                return redirect(url_for('admin_bp.admin_dashboard'))
            return redirect(url_for('user_bp.dashboard'))

        # GET request
        users = db.query(User).order_by(User.id).all()
        return render_template('login.html', users=users)
    finally:
        db.close()


@user_bp.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('user_bp.login'))


@user_bp.route('/dashboard')
@login_required
def dashboard():
    if session.get('role') == 'ADMINISTRATOR':
        return redirect(url_for('admin_bp.admin_dashboard'))

    db = get_db()
    try:
        # Get active shows count and user's bookings count
        shows_count = db.query(Resource).filter_by(status='ACTIVE').count()
        user_bookings_count = db.query(Reservation).filter_by(user_id=session.get('user_id')).count()
        return render_template('dashboard.html',
                               shows_count=shows_count,
                               user_bookings_count=user_bookings_count)
    finally:
        db.close()


@user_bp.route('/shows')
@login_required
def shows():
    db = get_db()
    try:
        query_text = request.args.get('search', '').strip()
        query = db.query(Resource).filter(Resource.status == 'ACTIVE')

        if query_text:
            query = query.filter(Resource.name.ilike(f"%{query_text}%") | Resource.id.ilike(f"%{query_text}%"))

        resources = query.order_by(Resource.id).all()
        return render_template('shows.html', resources=resources, search_query=query_text)
    finally:
        db.close()


@user_bp.route('/booking/<resource_id>', methods=['GET'])
@login_required
def booking(resource_id):
    if session.get('role') == 'ADMINISTRATOR':
        return redirect(url_for('admin_bp.admin_dashboard'))

    db = get_db()
    try:
        resource = db.query(Resource).filter_by(id=resource_id).first()
        if not resource:
            return render_template('error.html', error_message="This show is currently unavailable.", status_code=404), 404

        if not resource.is_active():
            return render_template('error.html', error_message="This show is currently unavailable.", status_code=400), 400

        # Calculate default initial values for 1 seat
        base_amount, booking_charge, grand_total = AvailabilityService.calculate_pricing(resource.rate, 1)

        return render_template('booking.html',
                               resource=resource,
                               base_amount=base_amount,
                               booking_charge=booking_charge,
                               grand_total=grand_total)
    finally:
        db.close()


@user_bp.route('/booking/confirm', methods=['POST'])
@login_required
def confirm_booking():
    if session.get('role') == 'ADMINISTRATOR':
        return redirect(url_for('admin_bp.admin_dashboard'))

    resource_id = request.form.get('resource_id', '').strip()
    raw_quantity = request.form.get('quantity')
    customer_name = request.form.get('name', '').strip()
    customer_phone = request.form.get('phone', '').strip()
    booking_date = request.form.get('booking_date', '').strip()
    reference_info = request.form.get('reference_info', '').strip()

    # --- BR1: Quantity Validation ---
    is_valid_qty, quantity, qty_msg = AvailabilityService.validate_quantity(raw_quantity)
    if not is_valid_qty:
        flash(qty_msg, "danger")
        return render_template('error.html', error_message=qty_msg, status_code=400), 400

    # --- BR5: Booking Details Validation ---
    if not customer_name:
        msg = "Name cannot be blank."
        flash(msg, "danger")
        return render_template('error.html', error_message=msg, status_code=400), 400

    if not re.match(r'^\d{10}$', customer_phone):
        msg = "Phone number must contain exactly 10 digits."
        flash(msg, "danger")
        return render_template('error.html', error_message=msg, status_code=400), 400

    if not booking_date:
        msg = "Booking details are invalid."
        flash(msg, "danger")
        return render_template('error.html', error_message=msg, status_code=400), 400

    # Validate booking_date format (YYYY-MM-DD)
    try:
        datetime.strptime(booking_date, '%Y-%m-%d')
    except ValueError:
        msg = "Booking details are invalid."
        flash(msg, "danger")
        return render_template('error.html', error_message=msg, status_code=400), 400

    if not reference_info:
        msg = "Booking details are invalid."
        flash(msg, "danger")
        return render_template('error.html', error_message=msg, status_code=400), 400

    # --- ATOMIC DATABASE TRANSACTION (BR2, BR3, BR4, BR6, BR7) ---
    db = get_db()
    try:
        # Re-check availability within transaction
        resource = db.query(Resource).filter_by(id=resource_id).first()
        if not resource:
            db.rollback()
            msg = "This show is currently unavailable."
            flash(msg, "danger")
            return render_template('error.html', error_message=msg, status_code=400), 400

        if not resource.is_active():
            db.rollback()
            msg = "This show is currently unavailable."
            flash(msg, "danger")
            return render_template('error.html', error_message=msg, status_code=400), 400

        if resource.availability <= 0:
            db.rollback()
            msg = "This show is currently unavailable."
            flash(msg, "danger")
            return render_template('error.html', error_message=msg, status_code=400), 400

        if resource.availability < quantity:
            db.rollback()
            msg = "Requested quantity is not available."
            flash(msg, "danger")
            return render_template('error.html', error_message=msg, status_code=400), 400

        # BR3 & BR4: Capture rate snapshot and calculate totals
        rate_snapshot = float(resource.rate)
        base_amount, booking_charge, grand_total = AvailabilityService.calculate_pricing(rate_snapshot, quantity)

        # Generate unique reservation ID
        booking_count = db.query(Reservation).count() + 1
        booking_id = f"RES-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{booking_count:04d}"

        # 1. Create exactly ONE CONFIRMED reservation
        reservation = Reservation(
            id=booking_id,
            user_id=session.get('user_id'),
            status='CONFIRMED',
            total_amount=grand_total,
            customer_name=customer_name,
            customer_phone=customer_phone,
            booking_date=booking_date,
            reference_info=reference_info,
            created_at=datetime.now(timezone.utc)
        )
        db.add(reservation)

        # 2. Save selected show/resource information, quantity, fare snapshot, amounts
        reservation_item = ReservationItem(
            reservation_id=booking_id,
            resource_id=resource.id,
            quantity=quantity,
            rate_snapshot=rate_snapshot,
            base_amount=base_amount,
            booking_charge=booking_charge,
            grand_total=grand_total
        )
        db.add(reservation_item)

        # 3. Reduce availability
        resource.availability -= quantity

        # 4. Record booking status history
        history = BookingStatusHistory(
            reservation_id=booking_id,
            actor_id=session.get('user_id'),
            old_status=None,
            new_status='CONFIRMED',
            event_at=datetime.now(timezone.utc)
        )
        db.add(history)

        # Commit transaction atomically
        db.commit()

        flash("Reservation confirmed successfully!", "success")
        return redirect(url_for('user_bp.booking_success', booking_id=booking_id))

    except Exception as e:
        db.rollback()
        msg = f"Booking failed: {str(e)}"
        return render_template('error.html', error_message=msg, status_code=500), 500
    finally:
        db.close()


@user_bp.route('/booking/success/<booking_id>')
@login_required
def booking_success(booking_id):
    db = get_db()
    try:
        reservation = db.query(Reservation).filter_by(id=booking_id).first()
        if not reservation:
            return render_template('error.html', error_message="Booking not found.", status_code=404), 404

        # Access check (BR10)
        if session.get('role') != 'ADMINISTRATOR' and reservation.user_id != session.get('user_id'):
            return render_template('error.html', error_message="You are not authorized to access this booking.", status_code=403), 403

        item = reservation.items[0] if reservation.items else None
        return render_template('booking_success.html', reservation=reservation, item=item)
    finally:
        db.close()


@user_bp.route('/my-bookings')
@login_required
def my_bookings():
    db = get_db()
    try:
        # Display only currently logged-in user's bookings (BR10, FR6)
        user_id = session.get('user_id')
        reservations = db.query(Reservation).filter_by(user_id=user_id).order_by(Reservation.created_at.desc()).all()
        return render_template('my_bookings.html', reservations=reservations)
    finally:
        db.close()


@user_bp.route('/booking/<booking_id>/details')
@login_required
def booking_details(booking_id):
    db = get_db()
    try:
        reservation = db.query(Reservation).filter_by(id=booking_id).first()
        if not reservation:
            return render_template('error.html', error_message="Booking not found.", status_code=404), 404

        # Access rule (BR10)
        if session.get('role') != 'ADMINISTRATOR' and reservation.user_id != session.get('user_id'):
            return render_template('error.html', error_message="You are not authorized to access this booking.", status_code=403), 403

        return render_template('booking_details.html', reservation=reservation)
    finally:
        db.close()


@user_bp.route('/booking/<booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """
    BR8, BR9, BR10 - Cancellation Transaction:
    Only a CONFIRMED booking can be cancelled by its owner.
    Availability is restored exactly ONCE.
    Status history is recorded.
    """
    db = get_db()
    try:
        reservation = db.query(Reservation).filter_by(id=booking_id).first()
        if not reservation:
            return render_template('error.html', error_message="Booking not found.", status_code=404), 404

        # BR10: User ownership check
        if reservation.user_id != session.get('user_id'):
            return render_template('error.html', error_message="You are not authorized to access this booking.", status_code=403), 403

        # BR8 & BR9: Check status eligibility
        if reservation.status == 'CANCELLED':
            msg = "Booking has already been cancelled."
            flash(msg, "warning")
            return render_template('error.html', error_message=msg, status_code=400), 400

        if reservation.status != 'CONFIRMED':
            msg = "Only confirmed bookings can be cancelled."
            flash(msg, "warning")
            return render_template('error.html', error_message=msg, status_code=400), 400

        # Perform atomic cancellation
        old_status = reservation.status
        reservation.status = 'CANCELLED'

        # Restore availability exactly ONCE
        for item in reservation.items:
            resource = db.query(Resource).filter_by(id=item.resource_id).first()
            if resource:
                resource.availability += item.quantity

        # Record status history
        history = BookingStatusHistory(
            reservation_id=reservation.id,
            actor_id=session.get('user_id'),
            old_status=old_status,
            new_status='CANCELLED',
            event_at=datetime.now(timezone.utc)
        )
        db.add(history)

        db.commit()
        flash("Booking cancelled successfully. Seats have been restored.", "success")
        return redirect(url_for('user_bp.my_bookings'))

    except Exception as e:
        db.rollback()
        return render_template('error.html', error_message=f"Cancellation error: {str(e)}", status_code=500), 500
    finally:
        db.close()
