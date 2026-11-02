#!/usr/bin/env python3
"""Start the local website or run an audit on Windows, macOS and Linux.

    uv run jev.py
    uv run jev.py audit --limit 50
    uv run jev.py audit --dry-run --limit 3
"""
from __future__ import annotations

import argparse
from functools import partial
import getpass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent


def public_path(url: str, root: Path = ROOT) -> bool:
    """Expose only the viewer, PDFs and audit outputs, never local credentials."""
    path = unquote(urlsplit(url).path).lstrip("/") or "index.html"
    parts = path.split("/")
    if any(part.startswith(".") or "\\" in part or ":" in part for part in parts):
        return False
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        return False
    if path in {"index.html", "viewer.css", "viewer.js", "results.csv"}:
        return True
    if parts[0] == "pdfs" and target.suffix.lower() == ".pdf":
        return True
    if parts[0].startswith("jev-audit-"):
        if len(parts) == 2 and parts[1] in {"results.csv", "dry-run.csv"}:
            return True
        if len(parts) == 3 and parts[1] == "excerpts" and target.suffix == ".txt":
            return True
    return False


class ViewerHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        if not public_path(self.path, Path(self.directory)):
            self.send_error(404, "Not found")
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def serve(port: int = 8000, open_browser: bool = True) -> int:
    handler = partial(ViewerHandler, directory=str(ROOT))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as error:
        print(f"Impossible de démarrer le site : {error}\nEssayez : uv run jev.py --port 8001", file=sys.stderr)
        return 1
    with server:
        url = f"http://127.0.0.1:{server.server_port}"
        print(f"Site : {url}\nModifier les fichiers, puis actualiser le navigateur.\nCtrl+C pour arrêter.", flush=True)
        if open_browser:
            try:
                webbrowser.open(url)
            except webbrowser.Error:
                print("Ouvrez cette adresse dans votre navigateur.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def audit(arguments: list[str]) -> int:
    if not arguments or arguments[0].startswith("-"):
        arguments = ["pdfs", *arguments]
    environment = os.environ.copy()
    needs_key = not any(arg in {"--dry-run", "--help", "-h"} for arg in arguments)
    if needs_key and not environment.get("TYPESAFE_API_KEY", "").strip():
        try:
            key = getpass.getpass("Clé API TypeSafe (saisie masquée) : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nClassification annulée.", file=sys.stderr)
            return 130
        if not key:
            print("Une clé API est nécessaire. Pour un test local, ajoutez --dry-run.", file=sys.stderr)
            return 2
        environment["TYPESAFE_API_KEY"] = key
    try:
        return subprocess.run(
            [sys.executable, str(ROOT / "jev_pdf_audit.py"), *arguments],
            cwd=ROOT,
            env=environment,
            check=False,
        ).returncode
    except KeyboardInterrupt:
        return 130


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments and arguments[0] == "audit":
        return audit(arguments[1:])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["serve"], default="serve", help="Ouvrir le site (par défaut)")
    parser.add_argument("--port", type=int, default=8000, help="Port du site (défaut : 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur automatiquement")
    args = parser.parse_args(arguments)
    if not 0 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 0 et 65535.")
    return serve(args.port, not args.no_browser)


if __name__ == "__main__":
    sys.exit(main())
