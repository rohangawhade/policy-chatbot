"""FastAPI application factory for PolicyPal.

Routes and middleware are registered here as they're built in later phases
(see IMPLEMENTATION_STATUS.md for what's wired so far).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from config import cors_config


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(title="PolicyPal", version="0.1.0")
    app.add_middleware(TenantContextMiddleware)
    # Added last so it's the outermost middleware layer -- CORS headers
    # (and the preflight OPTIONS response itself) must be present on
    # every response, including ones TenantContextMiddleware/route
    # handlers never reach (e.g. an auth failure). files/coding-standards.md
    # section 8: "CORS configured to allow only the frontend origin."
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
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
