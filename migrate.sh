#!/bin/bash
# Safe Alembic Migration Workflow for Rizara
# Usage: ./migrate.sh "Migration message"

set -e  # Exit immediately on error

if [ -z "$1" ]; then
    echo "Usage: $0 \"Migration message\""
    exit 1
fi

MESSAGE="$1"
ALEMBIC_CMD="alembic -c alembic.ini"

# 1️⃣ Backup current database
DB_NAME="rizara"
DB_USER="thumbi"
BACKUP_FILE="backups/rizara_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p backups
echo "Backing up database to $BACKUP_FILE..."
pg_dump -U $DB_USER -d $DB_NAME > $BACKUP_FILE
echo "Backup complete ✅"

# 2️⃣ Generate new migration
echo "Generating migration: $MESSAGE"
$ALEMBIC_CMD revision --autogenerate -m "$MESSAGE"
echo "Migration generated. Review the file in alembic/versions/ before upgrading."

# 3️⃣ Prompt user to review migration
read -p "Have you reviewed the migration file and verified it? (y/n) " CONFIRM
if [[ "$CONFIRM" != "y" ]]; then
    echo "Migration canceled. Review the file before running upgrade."
    exit 1
fi

# 4️⃣ Apply migration
echo "Applying migration..."
$ALEMBIC_CMD upgrade head
echo "Migration applied successfully ✅"

# 5️⃣ Optional: show current head
$ALEMBIC_CMD current
