"""
Helper utilities for session management, role verification, and database sessions.
"""
from functools import wraps
from flask import session, redirect, url_for, flash, render_template, request
import database_setup
from models.user import User


def get_db():
    """Context manager or session provider for DB operations."""
    return database_setup.SessionLocal()


def get_current_user(db_session=None):
    """Retrieve current logged-in user object or None."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    close_at_end = False
    if db_session is None:
        db_session = database_setup.SessionLocal()
        close_at_end = True
    try:
        user = db_session.query(User).filter_by(id=user_id).first()
        return user
    finally:
        if close_at_end:
            db_session.close()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash("Please log in to continue.", "warning")
            return redirect(url_for('user_bp.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash("Please log in to continue.", "warning")
            return redirect(url_for('user_bp.login'))
        if session.get('role') != 'ADMINISTRATOR':
            flash("You are not authorized to access this booking.", "danger")
            return render_template('error.html', error_message="You are not authorized to access this booking.", status_code=403), 403
        return f(*args, **kwargs)
    return decorated_function
