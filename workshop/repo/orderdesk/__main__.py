"""python -m orderdesk [port]: serves the API on localhost (default port 8040)."""

import sys
from wsgiref.simple_server import make_server

from .api import wsgi_app

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8040
print(f"OrderDesk API on http://127.0.0.1:{port}  (try /health, /orders/5001, /orders/5001/invoice)")
make_server("127.0.0.1", port, wsgi_app).serve_forever()
