#!/usr/bin/env python3
"""Loopback-only full-stack preview. This is not the production entry point."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import uvicorn
from starlette.responses import FileResponse
from starlette.routing import Route
from server.rooms.api import create_app
from server.rooms.store import Store
from tools.catalog import load_catalog


def preview_app(database, origin, clock=None):
    catalog = {'database': load_catalog(ROOT), 'equipment': json.loads((ROOT/'data/equipment.json').read_text())}
    store = Store(database, catalog, **({'clock':clock} if clock else {}))
    app = create_app(store, origin, secure=False, require_archiver=False)
    async def index(request):
        return FileResponse(ROOT / 'index.html', headers={'Cache-Control':'no-store'})
    app.router.routes.insert(0, Route('/', index))
    return app, store


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8914)
    parser.add_argument('--database',type=Path,default=ROOT/'test-results/preview-rooms.sqlite3')
    args=parser.parse_args()
    if not (1 <= args.port <= 65535):parser.error('Invalid port')
    app,_=preview_app(args.database,f'http://127.0.0.1:{args.port}')
    uvicorn.run(app,host='127.0.0.1',port=args.port,workers=1,access_log=False,proxy_headers=False)
