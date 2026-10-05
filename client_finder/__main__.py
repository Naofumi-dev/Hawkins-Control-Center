"""Run a credentialed, unsent research preview or the internal service."""

from __future__ import annotations

import argparse
import json
import os
import getpass
from pathlib import Path

from .configuration import ConfigurationError, configure, load_private_environment
from .providers import ProviderError
from .server import build_runner, main as serve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview", "serve", "configure", "database-setup", "acquisition-setup", "configure-integration"))
    parser.add_argument("--provider", help="Personal integration to configure privately")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--owner-id", help="Confirmed personal owner's Supabase Auth UUID (configure only)")
    parser.add_argument("--config", type=Path, help="Private connection JSON outside the source workspace")
    parser.add_argument("--apply", action="store_true", help="Apply the selected database upgrade after a verified backup")
    args = parser.parse_args()
    if args.apply and args.command not in ("database-setup", "acquisition-setup"):
        parser.error("--apply is only valid with a database setup command")
    try:
        if args.command == "configure":
            if not args.owner_id:
                parser.error("configure requires --owner-id")
            configure(args.owner_id, args.config)
            return
        load_private_environment(args.config)
        from .integration_setup import configure_integration, load_integration_environment
        load_integration_environment()
        if args.command == "configure-integration":
            if not args.provider:
                parser.error("configure-integration requires --provider")
            configure_integration(args.provider)
            return
        if args.command in ("database-setup", "acquisition-setup"):
            from .database_setup import prepare_database
            prepare_database(apply=args.apply, acquisition=args.command == "acquisition-setup")
            return
    except ConfigurationError as exc:
        parser.exit(2, f"Personal Hawkins setup: {exc}\n")
    except (OSError, ProviderError, getpass.GetPassWarning, EOFError):
        parser.exit(2, "Personal Hawkins setup could not be completed; check the private file, terminal input, and owned project API access. No credentials are printed.\n")
    except KeyboardInterrupt:
        parser.exit(130, "Personal Hawkins setup cancelled\n")
    if args.command == "serve":
        serve()
    else:
        missing = [name for name in (
            "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "BRAVE_SEARCH_API_KEY"
        ) if not os.environ.get(name)]
        if missing:
            parser.exit(2, "Client Finder preview unavailable; missing configuration: " + ", ".join(missing) + "\n")
        if not 1 <= args.limit <= 10:
            parser.exit(2, "Client Finder preview limit must be between 1 and 10\n")
        try:
            result = build_runner().run(limit=args.limit, preview=True).json()
        except (ProviderError, ValueError):
            parser.exit(2, "Client Finder preview unavailable; check provider access and configuration\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
