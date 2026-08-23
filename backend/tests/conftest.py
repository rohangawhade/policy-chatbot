"""Pre-import `litellm` with warnings suppressed, and undo its side effect
on `os.environ`.

`litellm` 1.63.x's own import chain triggers several third-party
`DeprecationWarning`s under Python 3.12 (a legacy-`Config`-style pydantic
model, `importlib.resources.open_text`) — none of it our code, all of it
inside `litellm` itself. `pyproject.toml`'s `filterwarnings` turns
`DeprecationWarning` into a hard error (files/coding-standards.md's
zero-deprecation-warnings bar), which would otherwise fail collection the
first time any test imports `litellm`. Importing it once here, before
pytest's warning filters are in effect for individual test modules, means
the module is already in `sys.modules` and re-imports elsewhere are
silent no-ops.

Separately, `litellm/__init__.py` unconditionally calls
`dotenv.load_dotenv()` at import time, which loads the repo-root `.env`
file straight into this process's real `os.environ` — indistinguishable
afterward from a genuinely exported env var, and permanent for the rest
of the process. That defeats every `_env_file=None` isolation in
`test_config.py` (which exists specifically to test config defaults
without this machine's local `.env`) for the rest of the session, the
moment anything imports `litellm`. Undo exactly what it added — any key
that already existed as a real env var is left untouched either way,
since `load_dotenv()` defaults to not overriding existing values.
"""

import os
import warnings

_env_before_litellm_import = set(os.environ)

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import litellm  # noqa: F401

for _key in set(os.environ) - _env_before_litellm_import:
    del os.environ[_key]
