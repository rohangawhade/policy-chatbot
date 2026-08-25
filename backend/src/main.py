"""FastAPI application factory for PolicyPal.

Routes and middleware are registered here as they're built in later phases
(see IMPLEMENTATION_STATUS.md for what's wired so far).
"""

from fastapi import FastAPI

from api.middleware.tenant_context import TenantContextMiddleware
from api.routes import auth_routes, document_routes, health_routes


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="PolicyPal", version="0.1.0")
    app.add_middleware(TenantContextMiddleware)
    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(document_routes.router)
    return app


app = create_app()
