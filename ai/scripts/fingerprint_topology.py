from __future__ import annotations

import numpy as np

def validate_strength(strength):
    if isinstance(strength, (bool, str)) or not np.isscalar(strength):
        raise ValueError('strength must be a finite number in [0,1]')
    strength=float(strength)
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('strength must be a finite number in [0,1]')
    return strength
