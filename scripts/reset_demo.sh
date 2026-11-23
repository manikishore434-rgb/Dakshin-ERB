#!/bin/sh
# Wipe the database and reload the Section 5 master data (users, BOM, opening stock).
rm -f data/oto.db && python -c "from app import create_app; create_app()" && echo "Database reset and seeded."
