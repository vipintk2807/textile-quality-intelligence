"""Start the local development server:  python run.py"""

from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Bound to the loopback interface only: this is a local, single-user application.
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("TQI_PORT", "5000")),
        debug=bool(app.config.get("DEBUG")),
    )
