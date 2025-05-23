import pymysql
import os
import json
from typing import List, Dict, Any, Tuple
from .interface import DatabaseInterface

class MySQLAdapter(DatabaseInterface):
    def __init__(self, config: Dict[str, Any], schema_path: str = None):
        self.config = config
        self.schema_path = schema_path
        self.conn = None
        
    def connect(self) -> None:
        self.conn = pymysql.connect(**self.config)
        
    def disconnect(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
            
    def execute_query(self, query: str) -> Tuple[List[Tuple], List[str]]:
        with self.conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description] if cursor.description else []
            return results, column_names
        
    def get_schema(self) -> Dict[str, Any]:
        if self.schema_path and os.path.exists(self.schema_path):
            with open(self.schema_path, 'r') as f:
                return json.load(f)
        return {}  # Return empty schema if not found 