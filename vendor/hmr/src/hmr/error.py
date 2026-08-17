"""`hmr.error` — Custom error types for the HMR service.

1:1 alignment with `~/deepseek-harness/vendor/hmr/src/error.ts`.

The upstream module is a small ``handleError`` helper that logs build
failures with code frames via ``@babel/code-frame``. The Python port
preserves the public error surface (HmrError) but drops the esbuild /
babel integration — those are deep-frontend concerns that the
``@deepseek-ai/esbuild`` / ``@babel/code-frame`` Node-only packages
don't translate to Python. Errors propagate to the caller instead.
"""

from __future__ import annotations


class HmrError(Exception):
    """Raised by the HMR service for invalid input or runtime failures.

    Used for:

    - "HMR is not active" — ``register_config`` called before service
      init completed.
    - "config path already registered" — duplicate registration.
    - "config watch parent is not a directory" — ``stat`` on the path's
      dirname returns a non-directory.
    - Loader not exposed (upstream ``--expose-internals is required``).
    """


__all__ = ["HmrError"]
