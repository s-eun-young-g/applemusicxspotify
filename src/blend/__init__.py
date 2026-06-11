"""blend — a cross-platform music blend for the pairs Spotify won't do for you.

Spotify already blends Spotify×Spotify. This fills the gap: Apple×Apple and
Spotify×Apple. Everything runs on a universal Profile, so a person's taste can
come from Apple Music (local, no account) or Spotify (OAuth), and any two
profiles blend the same way.
"""

from __future__ import annotations

from .blend import BlendResult, blend
from .profile import Artist, Profile, Track

__all__ = ["Profile", "Track", "Artist", "blend", "BlendResult", "read_apple"]

__version__ = "0.1.0"


def read_apple(path: str, user: str) -> Profile:
    """Convenience: build a Profile from an exported Apple Music library XML."""
    from .apple import read_library
    return read_library(path, user)
