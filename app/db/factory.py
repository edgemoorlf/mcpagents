from typing import Dict, Any
from .interface import DatabaseInterface
from .sqlite_adapter import SQLiteAdapter
from .mysql_adapter import MySQLAdapter

class DatabaseFactory:
    @staticmethod
    def create_database(config: Dict[str, Any]) -> DatabaseInterface:
        db_type = config.get('type', 'sqlite')
        if db_type == 'sqlite':
            return SQLiteAdapter(
                db_path=config['path'],
                schema_path=config.get('schema_path')
            )
        elif db_type == 'mysql':
            return MySQLAdapter(
                config=config['connection'],
                schema_path=config.get('schema_path')
            )
        else:
            raise ValueError(f"Unsupported database type: {db_type}") 