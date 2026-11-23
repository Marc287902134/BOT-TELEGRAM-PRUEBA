import logging
from .config import settings, validate_settings
from .db import init_db
from .bot import build_app

def main():
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    validate_settings()
    init_db()
    app = build_app()
    app.run_polling(drop_pending_updates=True, allowed_updates=["message","callback_query"])

if __name__ == "__main__":
    main()
