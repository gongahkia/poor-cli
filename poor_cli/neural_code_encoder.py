from __future__ import annotations

import warnings

warnings.warn(
    "poor_cli.neural_code_encoder is deprecated; use poor_cli.research.neural_code_encoder",
    DeprecationWarning,
    stacklevel=2,
)

from poor_cli.research.neural_code_encoder import *  # noqa: E402,F401,F403
