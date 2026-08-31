"""RAGAS evaluation runner (files/plan.md Step 12.2).

Runs every entry in data/eval/golden_dataset.json through a real,
running backend over HTTP (not by importing backend/src/ directly --
see eval/requirements.txt's module docstring-equivalent comment for
why: ragas transitively requires tenacity<9, which conflicts with the
backend's own tenacity>=9,<10), then scores each answer with RAGAS's
faithfulness/answer_relevancy/context_precision/context_recall,
judged by a real Groq LLM and Pinecone embeddings called directly.

Prerequisites (not done by this script):
    1. `docker compose up -d postgres redis backend celery-worker`
    2. `cd backend && python scripts/seed_data.py` (creates the 5 demo
       employers this dataset's `employer_id` slugs refer to, and
       uploads/ingests/embeds data/gov_pdfs/ + data/synthetic/ for
       real -- this IS the real document corpus being evaluated)
    3. A real `GROQ_API_KEY` and `PINECONE_API_KEY` in backend's `.env`

Usage:
    eval/.venv/Scripts/python.exe run_eval.py [--config eval_config.yaml] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from datasets import Dataset, Features, Sequence, Value
from dotenv import load_dotenv
from langchain_core.outputs import Generation, LLMResult
from pinecone import Pinecone
from ragas import evaluate
from ragas.embeddings.base import BaseRagasEmbeddings
from ragas.llms.base import BaseRagasLLM
from ragas.llms.prompt import PromptValue
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
from ragas.run_config import RunConfig
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

import litellm
from litellm.exceptions import APIConnectionError, RateLimitError, ServiceUnavailableError, Timeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# RAGAS's own internal concurrency (RunConfig.max_workers, default 16)
# fires that many judge-LLM calls at once -- confirmed via a real smoke
# test to trigger Groq rate-limit errors even on a single-row dataset.
# `_JUDGE_RUN_CONFIG` below throttles that down; this retry handles
# whatever still slips through, same retryable-exception set and
# backoff shape as backend/src/adapters/llm/litellm_adapter.py's own
# `_generation_retry` (files/coding-standards.md section 11), just
# reimplemented here rather than imported (this script's dependency
# tree is deliberately isolated from backend/src/, see this file's
# module docstring).
_RETRYABLE_LLM_ERRORS = (APIConnectionError, Timeout, RateLimitError, ServiceUnavailableError)
_judge_llm_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=2.0, max=30.0),
    retry=retry_if_exception_type(_RETRYABLE_LLM_ERRORS),
    reraise=True,
)

# seed_data.py's own `_slugify()` (name.lower(), spaces/commas/
# apostrophes stripped -- no hyphens) produces a DIFFERENT string than
# generate_synthetic_docs.py's `_slugify()` (regex-based, hyphenated),
# which is what this dataset's `employer_id` values use (Step 12.1's
# documented interpretation). This maps the dataset's hyphenated slug
# to the real seeded HR-contact email seed_data.py actually creates --
# a real, confirmed inconsistency between the two scripts' own slug
# conventions, not something to silently paper over by re-deriving one
# from the other.
_EMPLOYER_SLUG_TO_EMAIL = {
    "northwind-traders": "hr@northwindtraders.test",
    "globex-corporation": "hr@globexcorporation.test",
    "acme-manufacturing": "hr@acmemanufacturing.test",
    "initech-solutions": "hr@initechsolutions.test",
    "contoso-health-group": "hr@contosohealthgroup.test",
}
# Entries with `employer_id: null` (off-topic rejections, and a few
# employer-agnostic edge cases) are issued under this employer's
# session -- any employer works equally for these by design (Step
# 12.1's golden_dataset.json's own documented interpretation).
_DEFAULT_EMPLOYER_SLUG = "northwind-traders"


@dataclass
class EvalConfig:
    backend_url: str
    dataset_path: Path
    report_dir: Path
    seed_password: str
    judge_llm_model: str
    judge_llm_temperature: float
    judge_embedding_model: str
    thresholds: dict[str, float]
    skip_retrieval_metrics_for_categories: set[str]
    request_interval_seconds: float

    @classmethod
    def load(cls, path: Path) -> EvalConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        base = path.parent
        return cls(
            backend_url=raw["backend_url"],
            dataset_path=(base / raw["dataset_path"]).resolve(),
            report_dir=(base / raw["report_dir"]).resolve(),
            seed_password=raw["seed_password"],
            judge_llm_model=raw["judge_llm"]["model"],
            judge_llm_temperature=raw["judge_llm"]["temperature"],
            judge_embedding_model=raw["judge_embedding"]["model"],
            thresholds=dict(raw["thresholds"]),
            skip_retrieval_metrics_for_categories=set(
                raw.get("skip_retrieval_metrics_for_categories", [])
            ),
            request_interval_seconds=float(raw["request_interval_seconds"]),
        )


@dataclass(frozen=True)
class GoldenEntry:
    id: str
    query: str
    expected_answer: str
    employer_id: str | None
    policy_type: str | None
    difficulty: str
    category: str


def load_dataset(path: Path) -> list[GoldenEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [GoldenEntry(**entry) for entry in raw["entries"]]


class GroqRagasLLM(BaseRagasLLM):
    """Wraps a direct `litellm.acompletion()` call to Groq -- RAGAS's
    own native abstract base, not its LangChain `BaseLanguageModel`
    wrapper, so this stays a thin, dependency-light shim rather than
    fighting LangChain's own chat-model interface."""

    def __init__(self, model: str, temperature: float) -> None:
        super().__init__()
        self._model = model
        self._temperature = temperature

    def generate_text(
        self,
        prompt: PromptValue,
        n: int = 1,
        temperature: float | None = None,
        stop: list[str] | None = None,
        callbacks: Any = None,
    ) -> LLMResult:
        return asyncio.run(self.agenerate_text(prompt, n=n, temperature=temperature, stop=stop))

    async def agenerate_text(
        self,
        prompt: PromptValue,
        n: int = 1,
        temperature: float | None = None,
        stop: list[str] | None = None,
        callbacks: Any = None,
        is_async: bool = True,
    ) -> LLMResult:
        text = prompt.to_string()
        # Deliberately ignores a near-zero `temperature` ragas itself
        # might pass for "deterministic" scoring calls (its own default
        # is `1e-08`) and floors to `self._temperature` instead --
        # confirmed via a real, reproducible test that this exact model
        # (Groq's `openai/gpt-oss-20b`, a reasoning model) gets stuck in
        # an infinite repetitive reasoning loop at temperature <= ~0.05
        # on simple prompts (finish_reason="length", ~3000 reasoning
        # tokens burned, visible content empty); 0.1 reliably produces
        # correct, concise output on the identical prompt. A caller
        # explicitly asking for *more* randomness than the floor is
        # still honored.
        temp = self._temperature if temperature is None else max(temperature, self._temperature)
        generations = [
            Generation(text=await self._complete(text, temp, stop)) for _ in range(n)
        ]
        return LLMResult(generations=[generations])

    @_judge_llm_retry
    async def _complete(self, text: str, temperature: float, stop: list[str] | None) -> str:
        response = await litellm.acompletion(
            model=self._model,
            messages=[{"role": "user", "content": text}],
            temperature=temperature,
            # Groq's `openai/gpt-oss-*` models spend part of this
            # budget on hidden reasoning tokens before any visible
            # output -- confirmed (Step 11.2) to sometimes consume an
            # entire 1024-1500 budget and return empty content, worse
            # for RAGAS's own judge prompts (statement extraction,
            # verdict JSON) which run longer than this project's own
            # generation prompts.
            max_tokens=3000,
            stop=stop,
        )
        return response.choices[0].message.content or ""


class PineconeRagasEmbeddings(BaseRagasEmbeddings):
    """Wraps a direct Pinecone `inference.embed()` call -- same
    real API this project's own `PineconeEmbeddingAdapter`
    (backend/src/adapters/llm/) uses, reimplemented here rather than
    imported, to keep this script's dependency tree isolated from
    backend/src/'s own (see this file's module docstring)."""

    def __init__(self, pinecone_api_key: str, model: str) -> None:
        self._client = Pinecone(api_key=pinecone_api_key)
        self._model = model

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], input_type="query")[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, input_type="passage")

    def _embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        response = self._client.inference.embed(
            model=self._model,
            inputs=texts,
            parameters={"input_type": input_type, "truncate": "END"},
        )
        return [[float(value) for value in item["values"]] for item in response.data]


@dataclass
class QueryResult:
    entry: GoldenEntry
    answer: str
    contexts: list[str]
    error: str | None = None


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/auth/login", data={"username": email, "password": password}
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


async def _create_conversation(client: httpx.AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/chat/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    response.raise_for_status()
    conversation_id: str = response.json()["id"]
    return conversation_id


async def _send_message(
    client: httpx.AsyncClient, token: str, conversation_id: str, content: str
) -> tuple[str, list[str]]:
    tokens: list[str] = []
    contexts: list[str] = []
    async with client.stream(
        "POST",
        f"/api/chat/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"content": content},
        # 60s wasn't enough in a real run -- a powerful-tier
        # (groq/openai/gpt-oss-120b) generation under real Groq load
        # timed out at the old value with an empty exception message
        # (httpx.ReadTimeout's str() is blank), confirmed via a real
        # `--limit 5` run against the live backend.
        timeout=120.0,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line.removeprefix("data: "))
            if payload.get("done"):
                contexts = payload.get("contexts", [])
                break
            token_text = payload.get("token")
            if token_text:
                tokens.append(token_text)
    return "".join(tokens), contexts


def _employer_email(employer_id: str | None) -> str:
    slug = employer_id or _DEFAULT_EMPLOYER_SLUG
    return _EMPLOYER_SLUG_TO_EMAIL[slug]


async def run_queries(config: EvalConfig, entries: list[GoldenEntry]) -> list[QueryResult]:
    by_email: dict[str, list[GoldenEntry]] = {}
    for entry in entries:
        by_email.setdefault(_employer_email(entry.employer_id), []).append(entry)

    results: list[QueryResult] = []
    async with httpx.AsyncClient(base_url=config.backend_url) as client:
        for email, employer_entries in by_email.items():
            token = await _login(client, email, config.seed_password)
            conversation_id = await _create_conversation(client, token)
            logger.info(
                "employer_session_started email=%s query_count=%d", email, len(employer_entries)
            )
            for index, entry in enumerate(employer_entries):
                if index > 0:
                    await asyncio.sleep(config.request_interval_seconds)
                try:
                    answer, contexts = await _send_message(
                        client, token, conversation_id, entry.query
                    )
                    results.append(QueryResult(entry=entry, answer=answer, contexts=contexts))
                    logger.info("query_completed id=%s", entry.id)
                except Exception as exc:  # noqa: BLE001 -- one bad query must not abort the run
                    # `str(exc)` alone is frequently empty for httpx timeout
                    # errors (confirmed via a real run: a q004 failure logged
                    # as bare `error=`) -- the exception's type is often the
                    # only signal available, so it's always included.
                    error_detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                    results.append(QueryResult(entry=entry, answer="", contexts=[], error=error_detail))
                    logger.warning("query_failed id=%s error=%s", entry.id, error_detail)
    return results


_RAGAS_FEATURES = Features(
    {
        "question": Value("string"),
        "answer": Value("string"),
        # Explicit Sequence(Value("string")) -- Dataset.from_dict()'s own
        # type inference produces a generic `List` feature instead, which
        # ragas's validate_column_dtypes() rejects outright (a real,
        # confirmed error: "Dataset feature 'contexts' should be of type
        # Sequence[string], got <class 'datasets.features.features.List'>").
        "contexts": Sequence(Value("string")),
        "ground_truth": Value("string"),
    }
)


def _to_ragas_dataset(
    results: list[QueryResult], *, skip_categories: set[str]
) -> tuple[Dataset, list[QueryResult]]:
    scoreable = [r for r in results if r.error is None]
    records = {
        "question": [r.entry.query for r in scoreable],
        "answer": [r.answer for r in scoreable],
        "contexts": [
            r.contexts if r.contexts and r.entry.category not in skip_categories else [" "]
            for r in scoreable
        ],
        "ground_truth": [r.entry.expected_answer for r in scoreable],
    }
    return Dataset.from_dict(records, features=_RAGAS_FEATURES), scoreable


def build_report(
    config: EvalConfig, results: list[QueryResult], scores: dict[str, list[float]]
) -> dict[str, Any]:
    scoreable = [r for r in results if r.error is None]
    per_query = []
    for result, index in zip(scoreable, range(len(scoreable)), strict=True):
        entry = result.entry
        metrics = {name: values[index] for name, values in scores.items()}
        passed = all(
            metrics.get(name, 1.0) >= threshold
            for name, threshold in config.thresholds.items()
            if name in metrics
        )
        per_query.append(
            {
                "id": entry.id,
                "category": entry.category,
                "difficulty": entry.difficulty,
                "employer_id": entry.employer_id,
                "query": entry.query,
                "answer": result.answer,
                "metrics": metrics,
                "passed": passed,
            }
        )
    failed_queries = [r.entry.id for r in results if r.error is not None]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_entries": len(results),
        "scored_entries": len(scoreable),
        "failed_to_run": failed_queries,
        "thresholds": config.thresholds,
        "aggregate_metrics": {
            name: (sum(values) / len(values) if values else None) for name, values in scores.items()
        },
        "pass_rate": (
            sum(1 for q in per_query if q["passed"]) / len(per_query) if per_query else None
        ),
        "per_query": per_query,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="eval_config.yaml", type=Path)
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N entries.")
    return parser.parse_args()


async def _main(args: argparse.Namespace) -> int:
    config = EvalConfig.load(args.config)
    entries = load_dataset(config.dataset_path)
    if args.limit is not None:
        entries = entries[: args.limit]

    logger.info(
        "eval_run_started entry_count=%d backend_url=%s", len(entries), config.backend_url
    )
    start = time.monotonic()
    results = await run_queries(config, entries)

    dataset, scoreable = _to_ragas_dataset(
        results, skip_categories=config.skip_retrieval_metrics_for_categories
    )
    if len(scoreable) == 0:
        logger.error("no_scoreable_results")
        return 1

    judge_llm = GroqRagasLLM(config.judge_llm_model, config.judge_llm_temperature)
    judge_embeddings = PineconeRagasEmbeddings(
        _pinecone_api_key(), config.judge_embedding_model
    )
    # RAGAS's own concurrency (RunConfig.max_workers, default 16) fires
    # that many judge-LLM calls at once -- confirmed via a real smoke
    # test to trigger Groq rate-limit errors even scoring a single row.
    # 2 keeps sustained usage well under Groq's free-tier ~8000 TPM
    # ceiling (Step 11.2's same constraint) alongside `_judge_llm_retry`
    # above for whatever still slips through.
    run_config = RunConfig(max_workers=2, timeout=120)
    ragas_result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
        embeddings=judge_embeddings,
        run_config=run_config,
        raise_exceptions=False,
    )
    # `ragas_result[name]` (dict-style access on the `Result` object)
    # returns the *aggregate* mean, not per-row scores -- confirmed via
    # a real error ("'numpy.float64' object is not iterable"). Per-row
    # scores live in `to_pandas()`'s columns instead.
    scores_df = ragas_result.to_pandas()
    scores = {
        name: [float(value) for value in scores_df[name]]
        for name in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
    }

    report = build_report(config, results, scores)
    config.report_dir.mkdir(parents=True, exist_ok=True)
    report_path = config.report_dir / f"eval_report_{datetime.now(UTC):%Y%m%d_%H%M%S}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    duration_s = time.monotonic() - start
    logger.info(
        "eval_run_completed duration_s=%.1f pass_rate=%s report_path=%s",
        duration_s,
        report["pass_rate"],
        report_path,
    )
    print(json.dumps(report["aggregate_metrics"], indent=2))
    print(f"Pass rate: {report['pass_rate']}")
    print(f"Full report: {report_path}")

    thresholds_met = all(
        (report["aggregate_metrics"].get(name) or 0.0) >= threshold
        for name, threshold in config.thresholds.items()
    )
    return 0 if thresholds_met and not report["failed_to_run"] else 1


def _pinecone_api_key() -> str:
    import os

    key = os.environ.get("PINECONE_API_KEY")
    if not key:
        raise RuntimeError("PINECONE_API_KEY must be set (repo-root .env) to run evaluation.")
    return key


if __name__ == "__main__":
    # Same real secrets the backend itself reads (repo-root `.env`, not
    # `eval/`'s own directory) -- GROQ_API_KEY for the judge LLM,
    # PINECONE_API_KEY for judge embeddings. Loaded here rather than
    # requiring the caller to export them, matching how `config.py`
    # already reads this file automatically for local host-based dev.
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    sys.exit(asyncio.run(_main(_parse_args())))
