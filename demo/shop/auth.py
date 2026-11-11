"""Session tokens.

Planted problem (internal randomness): tokens use only 4,096 possible random
suffixes, so a batch of tokens sometimes contains a duplicate. No environment
condition causes this, so FlakeLab should report "unknown cause".
"""

import random


def new_session_token(user: str) -> str:
    return f"{user}-{random.randrange(4096):03x}"
