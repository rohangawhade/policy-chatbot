"""Seeds realistic demo data (files/plan.md Step 11.3):

- 1 admin account (superuser, sees every employer via the admin dashboard).
- 5 employers with realistic company names, each with one EMPLOYER-role
  login account (**interpretation, not literal spec**: plan.md's bullet
  list only names "employees," but without at least one EMPLOYER-role
  account per company, Step 10.8's employer portal would have no seeded
  account that could ever log into it -- a gap that reads as an
  oversight in the bullet list, not an intentional exclusion).
- 10-20 EMPLOYEE-role accounts per employer.
- One Policy per `PolicyType` per employer (5 policies x 5 employers).
- Randomized enrollments: each employee enrolled in 1-3 of their
  employer's policies.
- Unless --skip-ingestion: uploads a handful of real documents per
  employer through the actual `POST /api/documents/upload` endpoint (not
  a bespoke DB insert) so Celery ingestion dispatch, `APP_UPLOAD_DIR`
  placement, and versioning all go through the exact same path a real
  upload does. Documents come from `data/gov_pdfs/` (Step 11.1) and
  `data/synthetic/` (Step 11.2 -- likely still empty; that step is
  blocked on a missing ANTHROPIC_API_KEY/OPENAI_API_KEY as of this step,
  see IMPLEMENTATION_STATUS.md). Neither directory is required to exist.

Every seeded login account shares one fixed password
(`_SEED_PASSWORD` below) -- this is throwaway local/dev data, not
anything resembling a production credential.

Requires Postgres reachable at `DATABASE_URL` for all of the above.
Document upload additionally requires the real backend HTTP API running
and reachable at --api-base-url (default http://localhost:8000) --
`docker compose up -d postgres redis backend celery-worker` first, or
pass --skip-ingestion to seed only the database.

**Not idempotent**: company names and every seeded login email
(`admin@policypal.seed`, `hr@<company-slug>.test`, ...) are fixed, not
randomized, so re-running against a database that already has a prior
run's data fails outright on the `employees.email` unique constraint
rather than silently creating a second batch -- this script targets a
disposable local/demo database meant to be seeded once (or after being
reset), not a shared or repeatedly-reseeded one. Safe to run against a
schema that's already been migrated to head; nothing here assumes a
pristine, empty database beyond "no prior run of this script."

Usage:
    python scripts/seed_data.py [--skip-ingestion]
        [--api-base-url http://localhost:8000] [--docs-per-employer N]
        [--seed N]
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from adapters.persistence.database import async_session_factory  # noqa: E402
from adapters.persistence.employee_repo import PostgresEmployeeRepository  # noqa: E402
from adapters.persistence.employer_repo import PostgresEmployerRepository  # noqa: E402
from adapters.persistence.policy_repo import (  # noqa: E402
    PostgresEnrollmentRepository,
    PostgresPolicyRepository,
)
from core.domain.employee import Employee, UserRole  # noqa: E402
from core.domain.employer import Employer  # noqa: E402
from core.domain.policy import Enrollment, Policy, PolicyType  # noqa: E402
from core.services.auth_service import AuthService  # noqa: E402

logger = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOV_PDFS_DIR = _REPO_ROOT / "data" / "gov_pdfs"
_SYNTHETIC_DIR = _REPO_ROOT / "data" / "synthetic"

_SEED_PASSWORD = "SeedPass123!"

_COMPANY_NAMES = [
    "Northwind Traders",
    "Globex Corporation",
    "Acme Manufacturing",
    "Initech Solutions",
    "Contoso Health Group",
]

_FIRST_NAMES = [
    "Alice", "Bob", "Carla", "David", "Elena", "Frank", "Grace", "Hassan",
    "Iris", "James", "Katya", "Liam", "Maria", "Noah", "Olivia", "Priya",
    "Quinn", "Rosa", "Sam", "Tara", "Umar", "Vera", "Will", "Xin", "Yusuf", "Zoe",
]  # fmt: skip
_LAST_NAMES = [
    "Anderson", "Brooks", "Chen", "Davis", "Evans", "Fischer", "Garcia",
    "Hughes", "Ibrahim", "Johnson", "Kumar", "Lee", "Martinez", "Nguyen",
    "O'Brien", "Patel", "Quinn", "Rossi", "Santos", "Taylor",
]  # fmt: skip

_DOC_CONTENT_TYPES: dict[str, str] = {"pdf": "application/pdf"}


def _slugify(name: str) -> str:
    return name.lower().replace(" ", "").replace(",", "").replace("'", "")


@dataclass
class SeededEmployer:
    employer: Employer
    employer_contact: Employee
    employees: list[Employee]
    policies: list[Policy]


async def _seed_database(session: AsyncSession, rng: random.Random) -> list[SeededEmployer]:
    """Does not commit -- matches this codebase's Unit-of-Work convention
    (`files/plan.md` Step 3.5: repositories only ever `flush()`, the
    caller commits). `_main` below is the "caller" for a real run;
    `tests/test_seed_data.py` is the caller for a test, and never
    commits at all so `conftest.py`'s `db_session` fixture's rollback
    undoes everything automatically."""
    employee_repository = PostgresEmployeeRepository(session)
    employer_repository = PostgresEmployerRepository(session)
    policy_repository = PostgresPolicyRepository(session)
    enrollment_repository = PostgresEnrollmentRepository(session)

    hashed = AuthService.hash_password(_SEED_PASSWORD)

    admin = await employee_repository.create(
        Employee(
            employer_id=None,
            email="admin@policypal.seed",
            hashed_password=hashed,
            full_name="Seed Admin",
            role=UserRole.ADMIN,
        )
    )
    logger.info("seeded_admin", email=admin.email)

    seeded: list[SeededEmployer] = []
    for company_name in _COMPANY_NAMES:
        employer = await employer_repository.create(Employer(name=company_name))
        slug = _slugify(company_name)

        contact = await employee_repository.create(
            Employee(
                employer_id=employer.id,
                email=f"hr@{slug}.test",
                hashed_password=hashed,
                full_name=f"{company_name} HR",
                role=UserRole.EMPLOYER,
            )
        )

        policies = [
            await policy_repository.create(
                Policy(
                    employer_id=employer.id,
                    policy_type=policy_type,
                    name=f"{company_name} {policy_type.value.title()} Plan",
                )
            )
            for policy_type in PolicyType
        ]

        employee_count = rng.randint(10, 20)
        employees: list[Employee] = []
        for i in range(employee_count):
            first = rng.choice(_FIRST_NAMES)
            last = rng.choice(_LAST_NAMES)
            employee = await employee_repository.create(
                Employee(
                    employer_id=employer.id,
                    email=f"{first.lower()}.{last.lower()}{i}@{slug}.test",
                    hashed_password=hashed,
                    full_name=f"{first} {last}",
                    role=UserRole.EMPLOYEE,
                )
            )
            employees.append(employee)

            for policy in rng.sample(policies, k=rng.randint(1, 3)):
                await enrollment_repository.create(
                    Enrollment(employee_id=employee.id, policy_id=policy.id)
                )

        logger.info("seeded_employer", name=company_name, employees=employee_count, policies=5)
        seeded.append(
            SeededEmployer(
                employer=employer, employer_contact=contact, employees=employees, policies=policies
            )
        )

    return seeded


def _discover_sample_documents() -> list[Path]:
    documents: list[Path] = []
    for directory in (_GOV_PDFS_DIR, _SYNTHETIC_DIR):
        if directory.exists():
            documents.extend(sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix))
    return documents


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/auth/login", data={"username": email, "password": password})
    response.raise_for_status()
    access_token: str = response.json()["access_token"]
    return access_token


async def _upload_document(client: httpx.AsyncClient, token: str, path: Path) -> None:
    extension = path.suffix.removeprefix(".").lower()
    content_type = _DOC_CONTENT_TYPES.get(extension)
    if content_type is None:
        logger.warning("skipping_unsupported_document", path=str(path), extension=extension)
        return

    response = await client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"title": path.stem},
        files={"file": (path.name, path.read_bytes(), content_type)},
    )
    if response.status_code >= 400:
        logger.warning(
            "document_upload_failed",
            path=str(path),
            status=response.status_code,
            body=response.text,
        )
        return
    logger.info(
        "uploaded_document", employer_title=path.stem, document_id=response.json().get("id")
    )


async def _trigger_ingestion(
    seeded: list[SeededEmployer], *, backend_url: str, docs_per_employer: int
) -> None:
    documents = _discover_sample_documents()
    if not documents:
        logger.warning(
            "no_sample_documents_found",
            checked=[str(_GOV_PDFS_DIR), str(_SYNTHETIC_DIR)],
            hint="Run `make download-gov-docs` (Step 11.1) first, or pass --skip-ingestion.",
        )
        return

    async with httpx.AsyncClient(base_url=backend_url, timeout=60.0) as client:
        doc_index = 0
        for entry in seeded:
            try:
                token = await _login(client, entry.employer_contact.email, _SEED_PASSWORD)
            except httpx.HTTPError as exc:
                logger.warning(
                    "employer_login_failed",
                    employer=entry.employer.name,
                    error=str(exc),
                    hint="Is the backend API reachable at --api-base-url?",
                )
                continue

            for _ in range(docs_per_employer):
                if doc_index >= len(documents):
                    doc_index = 0
                await _upload_document(client, token, documents[doc_index])
                doc_index += 1


def _print_credentials(admin_email: str, seeded: list[SeededEmployer]) -> None:
    print(f"\nSeeded login credentials (password for all: {_SEED_PASSWORD}):")
    print(f"  admin     {admin_email}")
    for entry in seeded:
        print(f"  employer  {entry.employer_contact.email}  ({entry.employer.name})")
    if seeded and seeded[0].employees:
        total = sum(len(e.employees) for e in seeded)
        print(f"  employee  {seeded[0].employees[0].email}  (one example; {total} total)")


async def _main(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    async with async_session_factory() as session:
        seeded = await _seed_database(session, rng)
        await session.commit()

    if not args.skip_ingestion:
        await _trigger_ingestion(
            seeded, backend_url=args.backend_url, docs_per_employer=args.docs_per_employer
        )
    else:
        logger.info("skipped_ingestion", reason="--skip-ingestion passed")

    _print_credentials("admin@policypal.seed", seeded)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Seed the database only; don't upload documents.",
    )
    parser.add_argument(
        "--api-base-url",
        dest="backend_url",
        default="http://localhost:8000",
        help="Backend base URL for document upload.",
    )
    parser.add_argument(
        "--docs-per-employer",
        type=int,
        default=3,
        help="Documents to upload per employer (default 3).",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed, for reproducible data."
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(_main(_parse_args()))
