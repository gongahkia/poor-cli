from __future__ import annotations

import warnings

warnings.warn(
    "poor_cli.latent_communication is deprecated; use poor_cli.research.latent_communication",
    DeprecationWarning,
    stacklevel=2,
)

from poor_cli.research.latent_communication import *  # noqa: E402,F401,F403
