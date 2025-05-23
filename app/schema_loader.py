import os
import json
from typing import Dict, List, Optional
from app.config import ConfigManager


def load_schema(db_name: str = 'default', tables: Optional[List[str]] = None) -> Dict:
    """
    Load the schema for the given database name from its schema_path in config.
    Optionally, only return the schema for the specified tables.
    """
    config_manager = ConfigManager()
    db_config = config_manager.get_database_config(db_name)
    schema_path = db_config.get('schema_path')
    if not schema_path or not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found for database '{db_name}': {schema_path}")
    with open(schema_path, 'r') as f:
        full_schema = json.load(f)
    if tables:
        return {table: full_schema[table] for table in tables if table in full_schema}
    return full_schema


def compact_schema_for_llm(schema: Dict, max_desc_len: int = 120) -> Dict:
    """
    Filter and compact the schema for LLM use:
    - Remove deprecated columns
    - Keep only name, type, description for columns
    - Truncate long descriptions
    - Omit unnecessary fields (examples, constraints, usage, aggregation, etc.)
    - Keep foreign_keys and a short table_description
    """
    compact = {}
    for table, meta in schema.items():
        if table == 'llm_prompt_instructions':
            continue
        columns = []
        for col in meta.get('columns', []):
            if col.get('deprecated'):
                continue
            col_desc = col.get('description', '')
            if len(col_desc) > max_desc_len:
                col_desc = col_desc[:max_desc_len] + '...'
            columns.append({
                'name': col['name'],
                'type': col['type'],
                'description': col_desc
            })
        compact[table] = {
            'columns': columns,
            'foreign_keys': meta.get('foreign_keys', []),
            'table_description': meta.get('table_description', '')[:max_desc_len]
        }
    return compact 