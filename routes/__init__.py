"""
Routes package initialization.
"""
from routes.user_routes import user_bp
from routes.admin_routes import admin_bp

__all__ = ['user_bp', 'admin_bp']
