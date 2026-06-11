"""Command-line entry point.

  blend apple  --user sofia [-o sofia.json]      build a profile from Apple Music
  blend mix    a.json b.json [-o playlist.json]  blend two profiles
  blend spotify ...                              (M1 — not yet)
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .blend import blend as blend_profiles
from .profile import Profile


def _cmd_apple(args) -> int:
    import os

    from .apple import default_library_path, read_library

    path = args.xml or default_library_path()
    if path and not os.path.exists(path):
        print(f"blend: no such library XML: {path}", file=sys.stderr)
        return 2
    if not path:
        print(
            "blend: couldn't find an Apple Music library XML.\n"
            "  Export one: Music ▸ File ▸ Library ▸ Export Library…\n"
            "  or enable Music ▸ Settings ▸ Advanced ▸ "
            "'Share Library XML with other applications',\n"
            "  then pass it with --xml PATH.",
            file=sys.stderr,
        )
        return 2

    profile = read_library(path, args.user)
    out = args.output or f"{args.user}.json"
    profile.save(out)
    print(f"blend: wrote {out}  "
          f"({len(profile.tracks)} tracks, {len(profile.artists)} artists, "
          f"{len(profile.genres)} genres)")
    return 0


def _cmd_mix(args) -> int:
    a = Profile.load(args.a)
    b = Profile.load(args.b)
    result = blend_profiles(a, b, limit=args.limit)
    print(result.summary())
    if args.output:
        import json
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump({
                "users": list(result.users),
                "score": result.score,
                "breakdown": result.breakdown,
                "playlist": result.playlist,
            }, f, indent=2, ensure_ascii=False)
        print(f"\nblend: wrote {args.output}")
    return 0


def _cmd_spotify(args) -> int:
    print("blend: the Spotify reader is the next milestone (M1) and isn't wired "
          "up yet.\nFor now, blend Apple↔Apple profiles with `blend apple` + "
          "`blend mix`.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="blend",
        description="Cross-platform music blend (Apple×Apple, Spotify×Apple).",
    )
    parser.add_argument("--version", action="version", version=f"blend {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_apple = sub.add_parser("apple", help="build a profile from Apple Music (local)")
    p_apple.add_argument("--user", required=True, help="a name for this profile")
    p_apple.add_argument("--xml", help="path to exported Library XML (auto-detected if omitted)")
    p_apple.add_argument("-o", "--output", help="output profile path (default: <user>.json)")
    p_apple.set_defaults(func=_cmd_apple)

    p_mix = sub.add_parser("mix", help="blend two profiles")
    p_mix.add_argument("a", help="first profile.json")
    p_mix.add_argument("b", help="second profile.json")
    p_mix.add_argument("--limit", type=int, default=30, help="blend playlist size")
    p_mix.add_argument("-o", "--output", help="write the blend (score + playlist) as JSON")
    p_mix.set_defaults(func=_cmd_mix)

    p_spotify = sub.add_parser("spotify", help="(M1) build a profile from Spotify")
    p_spotify.set_defaults(func=_cmd_spotify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
