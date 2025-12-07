"""
Database Tools for poor-cli

Database inspection and management:
- db_schema: Introspect database schema
- query_data: Execute queries with safety checks
- migration_generate: Auto-generate migrations
- orm_model_sync: Sync ORM models with database
"""

import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class DatabaseType(Enum):
    """Supported databases"""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"


@dataclass
class TableSchema:
    """Database table schema"""
    name: str
    columns: List[Dict[str, str]] = field(default_factory=list)
    primary_key: Optional[str] = None
    indexes: List[str] = field(default_factory=list)


@dataclass
class DatabaseSchema:
    """Complete database schema"""
    database_type: DatabaseType
    tables: List[TableSchema] = field(default_factory=list)
    views: List[str] = field(default_factory=list)


class DatabaseInspector:
    """Inspect database schema"""

    def inspect_sqlite(self, db_path: Path) -> DatabaseSchema:
        """Inspect SQLite database"""
        import sqlite3

        schema = DatabaseSchema(database_type=DatabaseType.SQLITE)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = [row[0] for row in cursor.fetchall()]

            for table_name in table_names:
                # Get table info
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        'name': row[1],
                        'type': row[2],
                        'nullable': not row[3],
                        'default': row[4]
                    })

                schema.tables.append(TableSchema(
                    name=table_name,
                    columns=columns
                ))

            conn.close()

        except Exception as e:
            logger.error(f"Failed to inspect SQLite database: {e}")

        return schema

    def inspect_postgresql(self, connection_string: str) -> DatabaseSchema:
        """Inspect PostgreSQL database"""
        schema = DatabaseSchema(database_type=DatabaseType.POSTGRESQL)

        try:
            import psycopg2

            conn = psycopg2.connect(connection_string)
            cursor = conn.cursor()

            # Get tables
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """)

            table_names = [row[0] for row in cursor.fetchall()]

            for table_name in table_names:
                # Get columns
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = %s
                """, (table_name,))

                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        'name': row[0],
                        'type': row[1],
                        'nullable': row[2] == 'YES',
                        'default': row[3]
                    })

                schema.tables.append(TableSchema(
                    name=table_name,
                    columns=columns
                ))

            conn.close()

        except Exception as e:
            logger.error(f"Failed to inspect PostgreSQL: {e}")

        return schema


class MigrationGenerator:
    """Generate database migrations"""

    def generate_alembic_migration(
        self,
        workspace_root: Path,
        message: str
    ) -> Optional[str]:
        """Generate Alembic migration"""
        cmd = ["alembic", "revision", "--autogenerate", "-m", message]

        try:
            result = subprocess.run(
                cmd,
                cwd=workspace_root,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Extract migration file path
                output = result.stdout
                # Parse output for migration file
                logger.info(f"Generated migration: {message}")
                return output
            else:
                logger.error(f"Migration generation failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Failed to generate migration: {e}")
            return None

    def generate_django_migration(
        self,
        workspace_root: Path,
        app_name: str
    ) -> Optional[str]:
        """Generate Django migration"""
        cmd = ["python", "manage.py", "makemigrations", app_name]

        try:
            result = subprocess.run(
                cmd,
                cwd=workspace_root,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info(f"Generated Django migration for {app_name}")
                return result.stdout
            else:
                logger.error(f"Migration generation failed: {result.stderr}")
                return None

        except Exception as e:
            logger.error(f"Failed to generate migration: {e}")
            return None
