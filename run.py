import os
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import uvicorn

if __name__ == "__main__":
    dev_mode = os.environ.get("DEV") == "1"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=dev_mode,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )