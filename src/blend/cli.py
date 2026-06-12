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
    import os

    from .blend import group_blend

    if len(args.profiles) < 2:
        print("blend: mix needs at least two profiles.", file=sys.stderr)
        return 2
    profiles = [Profile.load(p) for p in args.profiles]
    if len(profiles) == 2:
        result = blend_profiles(profiles[0], profiles[1], limit=args.limit)
    else:
        result = group_blend(profiles, limit=args.limit)
    print(result.summary())

    if args.output:
        import json
        data = {"score": result.score, "playlist": result.playlist}
        if hasattr(result, "users"):                 # pairwise
            data["users"] = list(result.users)
            data["breakdown"] = result.breakdown
        else:                                         # group
            data["members"] = result.members
            data["pairwise"] = result.pairwise
            data["cohesion"] = result.cohesion
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nblend: wrote {args.output}")

    if args.to_spotify:
        client_id = args.client_id or os.environ.get("SPOTIFY_CLIENT_ID")
        if not client_id:
            print("blend: --to-spotify needs --client-id (or SPOTIFY_CLIENT_ID).",
                  file=sys.stderr)
            return 2
        from .playlist import spotify_export
        try:
            info = spotify_export(result, client_id, name=args.name, public=args.public)
        except RuntimeError as exc:
            print(f"blend: Spotify export failed: {exc}", file=sys.stderr)
            return 1
        print(f"\nSpotify playlist: {info['url']}  "
              f"({info['added']} added, {len(info['missed'])} not found)")
        for m in info["missed"]:
            print(f"  not found: {m}")

    if args.to_apple:
        from .playlist import apple_export
        try:
            info = apple_export(result, name=args.name)
        except RuntimeError as exc:
            print(f"blend: Apple Music export failed: {exc}", file=sys.stderr)
            return 1
        print(f"\nApple Music playlist '{info['playlist']}' created "
              f"({info['attempted']} tracks attempted from your library).")

    return 0


def _cmd_spotify(args) -> int:
    import os

    client_id = args.client_id or os.environ.get("SPOTIFY_CLIENT_ID")
    if not client_id:
        print(
            "blend: need a Spotify client ID (bring your own — it's free).\n"
            "  1. Create an app at https://developer.spotify.com/dashboard\n"
            "  2. Add this Redirect URI to the app: http://127.0.0.1:8888/callback\n"
            "  3. Pass --client-id <id>  (or set SPOTIFY_CLIENT_ID).",
            file=sys.stderr,
        )
        return 2

    from .spotify import read_spotify

    try:
        profile = read_spotify(client_id, args.user, time_range=args.time_range)
    except RuntimeError as exc:
        print(f"blend: {exc}", file=sys.stderr)
        return 1

    out = args.output or f"{args.user}.json"
    profile.save(out)
    print(f"blend: wrote {out}  "
          f"({len(profile.tracks)} tracks, {len(profile.artists)} artists, "
          f"{len(profile.genres)} genres)")
    return 0


def _cmd_transfer(args) -> int:
    import os

    if args.src == args.dst:
        print("blend: --from and --to must be different services.", file=sys.stderr)
        return 2
    client_id = args.client_id or os.environ.get("SPOTIFY_CLIENT_ID")
    if not client_id:
        print("blend: transfer needs a Spotify --client-id (or SPOTIFY_CLIENT_ID).",
              file=sys.stderr)
        return 2

    if args.src == "spotify" and args.dst == "apple":
        from .playlist import spotify_to_apple
        try:
            info = spotify_to_apple(client_id, args.playlist, new_name=args.name)
        except RuntimeError as exc:
            print(f"blend: transfer failed: {exc}", file=sys.stderr)
            return 1
        print(f"Apple Music playlist '{info['playlist']}' created from "
              f"{info['source_tracks']} Spotify tracks.")
        return 0

    if args.src == "apple" and args.dst == "spotify":
        from .apple import default_library_path
        from .playlist import apple_to_spotify
        xml = args.xml or default_library_path()
        if not xml or not os.path.exists(xml):
            print("blend: need the Apple library XML — pass --xml PATH.", file=sys.stderr)
            return 2
        try:
            info = apple_to_spotify(xml, args.playlist, client_id,
                                    new_name=args.name, public=args.public)
        except RuntimeError as exc:
            print(f"blend: transfer failed: {exc}", file=sys.stderr)
            return 1
        print(f"Spotify playlist: {info['url']}  "
              f"({info['added']} added, {len(info['missed'])} not found "
              f"from {info['source_tracks']} Apple tracks)")
        return 0

    print("blend: only spotify↔apple transfers are supported.", file=sys.stderr)
    return 2


def _cmd_serve(args) -> int:
    try:
        from .web import serve
        serve(port=args.port, profiles_dir=args.dir,
              open_browser=not args.no_browser)
    except RuntimeError as exc:        # Flask not installed
        print(f"blend: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nblend: stopped.")
    return 0


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

    p_mix = sub.add_parser("mix", help="blend two or more profiles")
    p_mix.add_argument("profiles", nargs="+", help="two or more profile.json files")
    p_mix.add_argument("--limit", type=int, default=30, help="blend playlist size")
    p_mix.add_argument("-o", "--output", help="write the blend (score + playlist) as JSON")
    p_mix.add_argument("--to-spotify", action="store_true",
                       help="create the blend as a Spotify playlist")
    p_mix.add_argument("--to-apple", action="store_true",
                       help="create the blend as an Apple Music playlist (macOS)")
    p_mix.add_argument("--client-id", help="Spotify client ID for --to-spotify "
                       "(or set SPOTIFY_CLIENT_ID)")
    p_mix.add_argument("--public", action="store_true",
                       help="make the Spotify playlist public (default: private)")
    p_mix.add_argument("--name", help="playlist name (default: 'blend: A × B')")
    p_mix.set_defaults(func=_cmd_mix)

    p_spotify = sub.add_parser("spotify", help="build a profile from Spotify (OAuth)")
    p_spotify.add_argument("--user", required=True, help="a name for this profile")
    p_spotify.add_argument("--client-id", help="your Spotify app client ID "
                           "(or set SPOTIFY_CLIENT_ID)")
    p_spotify.add_argument("--time-range", default="medium_term",
                           choices=["short_term", "medium_term", "long_term"],
                           help="listening window for 'top' data (default: medium_term)")
    p_spotify.add_argument("-o", "--output", help="output profile path (default: <user>.json)")
    p_spotify.set_defaults(func=_cmd_spotify)

    p_xfer = sub.add_parser("transfer", help="copy a playlist between Spotify and Apple Music")
    p_xfer.add_argument("--from", dest="src", required=True, choices=["spotify", "apple"])
    p_xfer.add_argument("--to", dest="dst", required=True, choices=["spotify", "apple"])
    p_xfer.add_argument("--playlist", required=True,
                        help="source playlist name (Spotify: also accepts a URL/ID)")
    p_xfer.add_argument("--name", help="name for the new playlist")
    p_xfer.add_argument("--client-id", help="Spotify client ID (or set SPOTIFY_CLIENT_ID)")
    p_xfer.add_argument("--xml", help="Apple library XML (for --from apple)")
    p_xfer.add_argument("--public", action="store_true",
                        help="make the new Spotify playlist public")
    p_xfer.set_defaults(func=_cmd_transfer)

    p_serve = sub.add_parser("serve", help="launch the local web GUI (no terminal needed)")
    p_serve.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    p_serve.add_argument("--dir", default=".", help="folder holding profile .json files")
    p_serve.add_argument("--no-browser", action="store_true",
                         help="don't auto-open the browser")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
