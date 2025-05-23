from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple

class DatabaseInterface(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database"""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection"""
        pass
    
    @abstractmethod
    def execute_query(self, query: str) -> Tuple[List[Tuple], List[str]]:
        """Execute a SQL query and return results and column names"""
        pass
    
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return the schema metadata for NL2SQL"""
        pass 