import pymysql
import json
import argparse
import yaml
import os
from typing import List, Dict, Any

def load_mysql_config(db_name: str, config_path: str = "config/databases.yaml") -> Dict[str, Any]:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    if db_name not in config:
        raise ValueError(f"Database profile '{db_name}' not found in {config_path}")
    db_profile = config[db_name]
    if db_profile.get("type") != "mysql":
        raise ValueError(f"Database profile '{db_name}' is not of type 'mysql'")
    conn_info = db_profile.get("connection")
    if not conn_info:
        raise ValueError(f"No connection info found for '{db_name}' in {config_path}")
    return conn_info

def get_table_schema(cursor, table_name: str) -> Dict[str, Any]:
    """
    Extract column info and basic metadata for a MySQL table.
    """
    cursor.execute(f"SHOW FULL COLUMNS FROM `{table_name}`;")
    columns = []
    for col in cursor.fetchall():
        columns.append({
            "name": col[0],
            "type": col[1],
            "description": col[8] or "",
            "constraints": "Primary key" if col[4] == "PRI" else ("Nullable" if col[6] == "YES" else "Non-null"),
            "examples": [],
        })
    # Try to get table comment
    cursor.execute(f"SHOW TABLE STATUS WHERE Name='{table_name}';")
    table_status = cursor.fetchone()
    table_description = table_status[17] if table_status and len(table_status) > 17 else ""
    return {
        "columns": columns,
        "table_description": table_description,
        "common_queries": [],
        "value_ranges": {},
        "foreign_keys": [],
    }

def get_foreign_keys(cursor, table_name: str) -> List[Dict[str, Any]]:
    """
    Try to extract foreign key info for a table.
    """
    cursor.execute(f"SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_NAME = %s AND TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL;", (table_name,))
    fks = []
    for row in cursor.fetchall():
        fks.append({
            "column": row[0],
            "references": {
                "table": row[1],
                "column": row[2]
            },
            "description": f"Foreign key to {row[1]}.{row[2]}"
        })
    return fks

def extract_schema(connection, tables: List[str]) -> Dict[str, Any]:
    schema = {}
    with connection.cursor() as cursor:
        for table in tables:
            table_schema = get_table_schema(cursor, table)
            table_schema["foreign_keys"] = get_foreign_keys(cursor, table)
            schema[table] = table_schema
    return schema

def main():
    parser = argparse.ArgumentParser(description="Export MySQL table schema to JSON for NL2SQL/LLM use.")
    parser.add_argument("--db_name", required=True, help="Database profile name in config/databases.yaml")
    parser.add_argument("--tables", required=True, help="Comma-separated list of tables to export")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    conn_info = load_mysql_config(args.db_name)
    connection = pymysql.connect(**conn_info)
    try:
        tables = [t.strip() for t in args.tables.split(",") if t.strip()]
        schema = extract_schema(connection, tables)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        print(f"Schema for tables {tables} exported to {args.output}")
    finally:
        connection.close()

if __name__ == "__main__":
    main() 