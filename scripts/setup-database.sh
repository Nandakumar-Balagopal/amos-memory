#!/bin/bash
# Setup script for AMOS PostgreSQL database

set -e  # Exit on error

echo "🚀 Setting up AMOS PostgreSQL database..."

# Configuration
DB_NAME="${AMOS_DB_NAME:-amos}"
DB_USER="${AMOS_DB_USER:-amos}"
DB_PASSWORD="${AMOS_DB_PASSWORD:-amos}"
DB_HOST="${AMOS_DB_HOST:-localhost}"
DB_PORT="${AMOS_DB_PORT:-5432}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"

# Set PGPASSWORD for non-interactive password
export PGPASSWORD="$POSTGRES_PASSWORD"

# Check if PostgreSQL is running
if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
    echo "❌ PostgreSQL is not running on $DB_HOST:$DB_PORT"
    echo ""
    echo "To start PostgreSQL:"
    echo "  macOS (Homebrew): brew services start postgresql@15"
    echo "  Linux (systemd): sudo systemctl start postgresql"
    echo "  Docker: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15"
    exit 1
fi

echo "✅ PostgreSQL is running"

# Create database user if it doesn't exist
echo "📝 Creating database user '$DB_USER'..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -tc "SELECT 1 FROM pg_user WHERE usename = '$DB_USER'" | grep -q 1 || \
    psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"

echo "✅ User '$DB_USER' ready"

# Create database if it doesn't exist
echo "📝 Creating database '$DB_NAME'..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
    psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

echo "✅ Database '$DB_NAME' ready"

# Grant privileges
echo "📝 Granting privileges..."
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

# Install pgvector extension (requires superuser)
echo "📝 Installing pgvector extension..."
export PGPASSWORD="$POSTGRES_PASSWORD"
psql -h "$DB_HOST" -p "$DB_PORT" -U postgres -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" || {
    echo "⚠️  Could not install pgvector extension. You may need to:"
    echo "   1. Install pgvector: brew install pgvector"
    echo "   2. Restart PostgreSQL: brew services restart postgresql@15"
    echo "   3. Or use Docker: docker run -d -p 5432:5432 pgvector/pgvector:pg15"
}

# Run migrations
echo "📝 Running migrations..."

# Set password for amos user
export PGPASSWORD="$DB_PASSWORD"

# Migration 001: Initial schema
echo "  → Running migration 001_initial.sql..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f migrations/001_initial.sql

# Migration 002: pgvector and hybrid retrieval
echo "  → Running migration 002_pgvector_hybrid_retrieval.sql..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f migrations/002_pgvector_hybrid_retrieval.sql

echo "✅ Migrations complete"

# Verify setup
echo "📝 Verifying setup..."
TABLES=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
EXTENSIONS=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector';")

echo "  Tables created: $TABLES"
echo "  pgvector installed: $EXTENSIONS"

if [ "$TABLES" -ge 4 ] && [ "$EXTENSIONS" -ge 1 ]; then
    echo "✅ Database setup complete!"
    echo ""
    echo "Connection string:"
    echo "  postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
    echo ""
    echo "Environment variables:"
    echo "  export AMOS_POSTGRES_DSN=\"postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME\""
    echo "  export AMOS_STORAGE_BACKEND=\"postgres\""
else
    echo "⚠️  Setup may be incomplete. Please check the output above."
    exit 1
fi

# Made with Bob
