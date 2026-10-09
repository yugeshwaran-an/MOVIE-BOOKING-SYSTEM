"""
Administrator routes handling booking overviews and strict status workflow progression.
"""
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.resource import Resource
from models.reservation import Reservation
from models.booking_status_history import BookingStatusHistory
from routes.helpers import get_db, admin_required

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')


@admin_bp.route('/dashboard')
@admin_required
def admin_dashboard():
    db = get_db()
    try:
        # Display all bookings across all users
        reservations = db.query(Reservation).order_by(Reservation.created_at.desc()).all()
        resources = db.query(Resource).order_by(Resource.id).all()
        return render_template('admin_dashboard.html',
                               reservations=reservations,
                               resources=resources)
    finally:
        db.close()


@admin_bp.route('/booking/<booking_id>/status', methods=['POST'])
@admin_required
def update_booking_status(booking_id):
    """
    BR8 - Advance booking status ONLY to the next valid status:
    CONFIRMED -> CHECKED_IN -> COMPLETED
    and
    CONFIRMED -> CANCELLED

    Reject:
    - CONFIRMED -> COMPLETED
    - CONFIRMED -> CANCELLED -> COMPLETED
    - COMPLETED -> CANCELLED
    - CANCELLED -> CONFIRMED
    """
    new_status = request.form.get('new_status', '').strip()
    db = get_db()
    try:
        reservation = db.query(Reservation).filter_by(id=booking_id).first()
        if not reservation:
            flash("Booking not found.", "danger")
            return render_template('error.html', error_message="Booking not found.", status_code=404), 404

        current_status = reservation.status
        valid_next = reservation.get_valid_next_statuses()

        if new_status not in valid_next:
            msg = "Invalid booking status transition."
            flash(msg, "danger")
            return render_template('error.html', error_message=msg, status_code=400), 400

        # Perform valid status transition
        reservation.status = new_status

        # If transitioning to CANCELLED, restore capacity exactly once
        if new_status == 'CANCELLED':
            for item in reservation.items:
                resource = db.query(Resource).filter_by(id=item.resource_id).first()
                if resource:
                    resource.availability += item.quantity

        # Record audit history
        history = BookingStatusHistory(
            reservation_id=reservation.id,
            actor_id=session.get('user_id', 'admin'),
            old_status=current_status,
            new_status=new_status,
            event_at=datetime.now(timezone.utc)
        )
        db.add(history)

        db.commit()
        flash(f"Booking {booking_id} status updated from {current_status} to {new_status}.", "success")
        return redirect(url_for('admin_bp.admin_dashboard'))

    except Exception as e:
        db.rollback()
        return render_template('error.html', error_message=f"Status update error: {str(e)}", status_code=500), 500
    finally:
        db.close()


@admin_bp.route('/movie/create', methods=['GET', 'POST'])
@admin_required
def create_movie():
    """Admin endpoint to create a new movie listing and schedule."""
    if request.method == 'GET':
        db = get_db()
        try:
            # Suggest next Show ID
            existing_resources = db.query(Resource).all()
            max_num = 100
            for r in existing_resources:
                if r.id.startswith('R') and r.id[1:].isdigit():
                    max_num = max(max_num, int(r.id[1:]))
            suggested_id = f"R{max_num + 1}"
            return render_template('admin_create_movie.html', suggested_id=suggested_id)
        finally:
            db.close()

    # Handle POST
    db = get_db()
    try:
        name = request.form.get('name', '').strip()
        custom_id = request.form.get('id', '').strip()
        rate_str = request.form.get('rate', '').strip()
        availability_str = request.form.get('availability', '').strip()
        show_date = request.form.get('show_date', '').strip()
        show_time = request.form.get('show_time', '').strip()
        category = request.form.get('category', '').strip()
        status = request.form.get('status', 'ACTIVE').strip()

        if not name:
            flash("Movie name cannot be empty.", "danger")
            return redirect(url_for('admin_bp.create_movie'))

        # Auto-generate ID if not provided
        if not custom_id:
            existing_resources = db.query(Resource).all()
            max_num = 100
            for r in existing_resources:
                if r.id.startswith('R') and r.id[1:].isdigit():
                    max_num = max(max_num, int(r.id[1:]))
            custom_id = f"R{max_num + 1}"
        else:
            custom_id = custom_id.upper()
            if db.query(Resource).filter_by(id=custom_id).first():
                flash(f"A show with ID '{custom_id}' already exists. Please choose a different ID.", "danger")
                return redirect(url_for('admin_bp.create_movie'))

        # Validate Rate
        try:
            rate = float(rate_str)
            if rate <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            flash("Ticket rate must be a positive number.", "danger")
            return redirect(url_for('admin_bp.create_movie'))

        # Validate Availability
        try:
            availability = int(availability_str)
            if availability < 0:
                raise ValueError()
        except (ValueError, TypeError):
            flash("Seat availability must be a non-negative integer.", "danger")
            return redirect(url_for('admin_bp.create_movie'))

        if not show_date or not show_time:
            flash("Show date and time are required.", "danger")
            return redirect(url_for('admin_bp.create_movie'))

        if not category:
            category = "Standard Screening"

        # Create new Resource
        new_resource = Resource(
            id=custom_id,
            name=name,
            rate=rate,
            availability=availability,
            status=status if status in ['ACTIVE', 'INACTIVE'] else 'ACTIVE'
        )
        db.add(new_resource)
        db.flush()

        # Create Schedule
        from models.schedule import Schedule
        new_schedule = Schedule(
            resource_id=new_resource.id,
            date=show_date,
            time=show_time,
            category=category
        )
        db.add(new_schedule)

        db.commit()
        flash(f"Movie '{name}' (ID: {custom_id}) successfully added to active shows!", "success")
        return redirect(url_for('admin_bp.admin_dashboard'))

    except Exception as e:
        db.rollback()
        flash(f"Error creating movie: {str(e)}", "danger")
        return redirect(url_for('admin_bp.create_movie'))
    finally:
        db.close()


@admin_bp.route('/movie/<movie_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_movie_status(movie_id):
    """Toggle ACTIVE / INACTIVE status for a movie."""
    db = get_db()
    try:
        resource = db.query(Resource).filter_by(id=movie_id).first()
        if not resource:
            flash("Movie not found.", "danger")
            return redirect(url_for('admin_bp.admin_dashboard'))

        resource.status = 'INACTIVE' if resource.status == 'ACTIVE' else 'ACTIVE'
        db.commit()
        flash(f"Status for '{resource.name}' updated to {resource.status}.", "info")
        return redirect(url_for('admin_bp.admin_dashboard'))
    finally:
        db.close()


@admin_bp.route('/movie/<movie_id>/delete', methods=['POST'])
@admin_required
def delete_movie(movie_id):
    """Delete a movie if it has no confirmed reservations, or mark inactive."""
    db = get_db()
    try:
        resource = db.query(Resource).filter_by(id=movie_id).first()
        if not resource:
            flash("Movie not found.", "danger")
            return redirect(url_for('admin_bp.admin_dashboard'))

        # Check if there are reservations referencing this resource
        if resource.reservation_items:
            # Has booking history; deactivate rather than hard delete to preserve referential integrity
            resource.status = 'INACTIVE'
            db.commit()
            flash(f"'{resource.name}' has existing booking records, so its status was set to INACTIVE instead of deleting.", "warning")
        else:
            movie_title = resource.name
            db.delete(resource)
            db.commit()
            flash(f"Movie '{movie_title}' (ID: {movie_id}) was successfully deleted.", "success")

        return redirect(url_for('admin_bp.admin_dashboard'))
    except Exception as e:
        db.rollback()
        flash(f"Error deleting movie: {str(e)}", "danger")
        return redirect(url_for('admin_bp.admin_dashboard'))
    finally:
        db.close()

