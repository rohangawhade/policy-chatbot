"""FastAPI application factory for PolicyPal.

Routes and middleware are registered here as they're built in later phases
(see IMPLEMENTATION_STATUS.md for what's wired so far).
"""

from fastapi import FastAPI

from api.middleware.tenant_context import TenantContextMiddleware
from api.routes import (
    admin_routes,
    auth_routes,
    chat_routes,
    document_routes,
    employee_routes,
    employer_routes,
    feedback_routes,
    health_routes,
    policy_routes,
)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="PolicyPal", version="0.1.0")
    app.add_middleware(TenantContextMiddleware)
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(document_routes.router)
    app.include_router(employer_routes.router)
    app.include_router(employee_routes.router)
    app.include_router(policy_routes.router)
    app.include_router(feedback_routes.router)
    app.include_router(admin_routes.router)
    return app


app = create_app()
