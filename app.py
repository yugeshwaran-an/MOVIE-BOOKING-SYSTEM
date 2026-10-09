"""
Movie Ticket Booking System - Flask Application Entrypoint
Software Engineering SAT-II Practical Assessment
"""
import os
from flask import Flask, render_template, session
from database_setup import init_db
from routes.user_routes import user_bp
from routes.admin_routes import admin_bp


def create_app():
    """Application factory for the Movie Ticket Booking System."""
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'movie-ticket-booking-sat2-secret-key-2026')

    # Register blueprints
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)

    # Context processor for templates
    @app.context_processor
    def inject_user_context():
        return {
            'session_user_id': session.get('user_id'),
            'session_username': session.get('username'),
            'session_name': session.get('name'),
            'session_role': session.get('role'),
            'is_admin': session.get('role') == 'ADMINISTRATOR',
            'is_user': session.get('role') == 'USER'
        }

    # Custom HTTP error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', error_message="The requested page or resource could not be found.", status_code=404), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('error.html', error_message="You are not authorized to access this booking.", status_code=403), 403

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', error_message="An internal server error occurred.", status_code=500), 500

    return app


# Initialize database with schema and seed data upon startup
init_db(reseed=False)
app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("Starting Movie Ticket Booking System")
    print("Database: SQLite (database.db)")
    print("Access application at: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5000, debug=True)
