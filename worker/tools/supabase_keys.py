"""
Own keys for the local Supabase stack (F7, pilot through the tunnel).

The CLI's default keys are the same on every machine: with the API public,
anyone could sign a service_role token. This keeps a random JWT secret and
publishable / secret keys in supabase/.env (read by supabase/config.toml) and
copies the keys the stack derives from them into the web's .env.local.

Usage (from worker/, stack running for `sync`):
    python -m tools.supabase_keys generate     # add the missing ones to supabase/.env
    python -m tools.supabase_keys generate --rotate   # new ones (logs everybody out)
    # then: npx supabase stop; npx supabase start   (from the repo root)
    python -m tools.supabase_keys sync         # web/.env.local ← `supabase status`
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path

from config import ROOT

SUPABASE_ENV = ROOT / "supabase" / ".env"
WEB_ENV = ROOT / "web" / ".env.local"


def new_keys() -> dict[str, str]:
    return {
        "JWT_SECRET": secrets.token_urlsafe(48),
        "SUPABASE_PUBLISHABLE_KEY": f"sb_publishable_{secrets.token_urlsafe(24)}",
        "SUPABASE_SECRET_KEY": f"sb_secret_{secrets.token_urlsafe(24)}",
    }


def set_vars(text: str, values: dict[str, str], *, overwrite: bool = True) -> str:
    """`text` (a .env file) with each KEY=value set: replaced in place, or appended."""
    for key, value in values.items():
        line = f"{key}={value}"
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(text):
            if overwrite:
                text = pattern.sub(lambda _: line, text)
        else:
            text = (text if text.endswith("\n") or not text else text + "\n") + line + "\n"
    return text


def generate(rotate: bool) -> None:
    text = SUPABASE_ENV.read_text(encoding="utf-8") if SUPABASE_ENV.exists() else ""
    SUPABASE_ENV.write_text(set_vars(text, new_keys(), overwrite=rotate), encoding="utf-8", newline="\n")
    print(f"{SUPABASE_ENV}: claves {'nuevas' if rotate else 'completas'}. "
          "Reiniciá el stack (npx supabase stop; npx supabase start) y corré `sync`.")


def sync() -> None:
    out = subprocess.run("npx supabase status -o json", cwd=ROOT, shell=True, check=True,
                         capture_output=True, text=True).stdout
    status = json.loads(out[out.index("{"):])
    if status["JWT_SECRET"].startswith("super-secret"):
        raise SystemExit("el stack usa las claves de demo: corré `generate` y reiniciá el stack")
    text = WEB_ENV.read_text(encoding="utf-8") if WEB_ENV.exists() else ""
    WEB_ENV.write_text(set_vars(text, {"NEXT_PUBLIC_SUPABASE_ANON_KEY": status["ANON_KEY"],
                                       "SUPABASE_SERVICE_ROLE_KEY": status["SERVICE_ROLE_KEY"]}),
                       encoding="utf-8", newline="\n")
    worker_env = ROOT / ".env"
    if worker_env.exists() and re.search(r"^SUPABASE_SERVICE_ROLE_KEY=", worker_env.read_text(encoding="utf-8"), re.M):
        worker_env.write_text(set_vars(worker_env.read_text(encoding="utf-8"),
                                       {"SUPABASE_SERVICE_ROLE_KEY": status["SERVICE_ROLE_KEY"]}),
                              encoding="utf-8", newline="\n")
    print(f"{WEB_ENV}: claves actualizadas. Reiniciá la web (o rehacé el build en producción).")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="Claves propias del Supabase local")
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--rotate", action="store_true")
    sub.add_parser("sync")
    args = parser.parse_args()
    generate(args.rotate) if args.cmd == "generate" else sync()
    return 0


if __name__ == "__main__":
    sys.exit(main())
