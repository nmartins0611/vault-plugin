"""Burger counter web app. Reads DB settings from /etc/myapp/config.ini on each request."""

from __future__ import annotations

import configparser
import html
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Sequence, Tuple

import psycopg2
from psycopg2 import Error as PostgresError
from psycopg2.extensions import connection as PgConnection


CONFIG_PATH = "/etc/myapp/config.ini"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8080


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str
    dbname: str


@dataclass(frozen=True)
class YearCount:
    year: int
    burgers: int


def load_database_config(path: str) -> DatabaseConfig:
    parser = configparser.ConfigParser()
    read_files = parser.read(path)
    if not read_files:
        raise RuntimeError(f"Could not read {path}")
    if not parser.has_section("database"):
        raise RuntimeError(f"{path} is missing a [database] section")
    return DatabaseConfig(
        host=parser.get("database", "host"),
        port=parser.getint("database", "port"),
        user=parser.get("database", "user"),
        password=parser.get("database", "password"),
        dbname=parser.get("database", "dbname"),
    )


def connect_database(config: DatabaseConfig) -> PgConnection:
    return psycopg2.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        dbname=config.dbname,
        connect_timeout=5,
    )


def current_utc_year(now: datetime) -> int:
    return now.astimezone(timezone.utc).year


def fetch_year_counts(conn: PgConnection) -> List[YearCount]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT EXTRACT(YEAR FROM eaten_at)::int AS year, COUNT(*)::int AS burgers
            FROM burger_log
            GROUP BY year
            ORDER BY year DESC
            """
        )
        rows: Sequence[Tuple[int, int]] = cursor.fetchall()
    return [YearCount(year=row[0], burgers=row[1]) for row in rows]


def count_for_year(counts: Sequence[YearCount], year: int) -> int:
    for item in counts:
        if item.year == year:
            return item.burgers
    return 0


def insert_burger(conn: PgConnection) -> None:
    with conn.cursor() as cursor:
        cursor.execute("INSERT INTO burger_log DEFAULT VALUES")
    conn.commit()


def render_page(
    year: int,
    year_total: int,
    history: Sequence[YearCount],
    db_host: str,
    error_message: str,
) -> str:
    history_rows = "".join(
        f"<tr><td>{item.year}</td><td>{item.burgers}</td></tr>" for item in history
    )
    if not history_rows:
        history_rows = "<tr><td colspan='2'>No burgers logged yet.</td></tr>"
    error_block = ""
    if error_message:
        error_block = f'<p class="error">{html.escape(error_message)}</p>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nostromo Burger Counter</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      margin: 0;
      min-height: 100vh;
      background: #1a1410;
      color: #f4e6d4;
    }}
    main {{
      max-width: 40rem;
      margin: 0 auto;
      padding: 3rem 1.5rem;
    }}
    h1 {{ font-size: 1.75rem; margin: 0 0 0.5rem; }}
    .lede {{ color: #c4b09a; margin-bottom: 2rem; }}
    .stat {{
      background: #2a211a;
      border: 1px solid #4a3a2c;
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }}
    .number {{ font-size: 4rem; font-weight: 700; line-height: 1; color: #e8a35a; }}
    button {{
      background: #e8a35a;
      color: #1a1410;
      border: 0;
      border-radius: 8px;
      padding: 0.75rem 1.25rem;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
    }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1.5rem; }}
    th, td {{ text-align: left; padding: 0.5rem 0; border-bottom: 1px solid #4a3a2c; }}
    .meta {{ margin-top: 2rem; color: #8a7664; font-size: 0.875rem; }}
    .error {{
      background: #3a1c16;
      border: 1px solid #a34a3a;
      color: #f2c4bc;
      padding: 0.75rem 1rem;
      border-radius: 8px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Burgers eaten in {year}</h1>
    <p class="lede">Logged on rhel01, stored in PostgreSQL on rhel03. Database password comes from Vault via <code>/etc/myapp/config.ini</code>.</p>
    {error_block}
    <div class="stat">
      <div class="number">{year_total}</div>
      <p>burgers this year</p>
      <form method="post" action="/eat">
        <button type="submit">I ate a burger</button>
      </form>
    </div>
    <h2>By year</h2>
    <table>
      <thead><tr><th>Year</th><th>Burgers</th></tr></thead>
      <tbody>{history_rows}</tbody>
    </table>
    <p class="meta">Database host: {html.escape(db_host)}</p>
  </main>
</body>
</html>
"""


def render_error_page(message: str) -> str:
    return render_page(
        year=current_utc_year(datetime.now(timezone.utc)),
        year_total=0,
        history=[],
        db_host="unavailable",
        error_message=message,
    )


def build_counts_page() -> str:
    config = load_database_config(CONFIG_PATH)
    conn = connect_database(config)
    try:
        now = datetime.now(timezone.utc)
        year = current_utc_year(now)
        history = fetch_year_counts(conn)
        return render_page(
            year=year,
            year_total=count_for_year(history, year),
            history=history,
            db_host=config.host,
            error_message="",
        )
    finally:
        conn.close()


def record_burger() -> None:
    config = load_database_config(CONFIG_PATH)
    conn = connect_database(config)
    try:
        insert_burger(conn)
    finally:
        conn.close()


def drain_request_body(handler: BaseHTTPRequestHandler) -> None:
    length_header = handler.headers.get("Content-Length")
    if length_header is None:
        return
    handler.rfile.read(int(length_header))


class BurgerHandler(BaseHTTPRequestHandler):
    def _write_html(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _write_failure(self, exc: BaseException) -> None:
        self._write_html(503, render_error_page(str(exc)))

    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        try:
            self._write_html(200, build_counts_page())
        except (RuntimeError, PostgresError) as exc:
            self._write_failure(exc)

    def do_POST(self) -> None:
        drain_request_body(self)
        if self.path != "/eat":
            self.send_error(404)
            return
        try:
            record_burger()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        except (RuntimeError, PostgresError) as exc:
            self._write_failure(exc)


def main() -> None:
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), BurgerHandler)
    print(f"Burger counter listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
