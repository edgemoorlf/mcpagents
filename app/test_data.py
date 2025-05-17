import os
import sqlite3
from app.process_and_aggregate import (
    process_table, 
    SCHEMA, 
    fetch_api_data,
    get_table_stats,
    print_table_stats
)

# Test database path
TEST_DB_FILE = 'data/test_model_stats.db'

# Real session ID provided by the user
SESSION_ID = "MTc0NzQ1MDIwMXxEWDhFQVFMX2dBQUJFQUVRQUFEX2p2LUFBQVVHYzNSeWFXNW5EQW9BQ0hWelpYSnVZVzFsQm5OMGNtbHVad3dHQUFSeWIyOTBCbk4wY21sdVp3d0dBQVJ5YjJ4bEEybHVkQVFEQVBfSUJuTjBjbWx1Wnd3SUFBWnpkR0YwZFhNRGFXNTBCQUlBQWdaemRISnBibWNNQndBRlozSnZkWEFHYzNSeWFXNW5EQWtBQjJSbFptRjFiSFFHYzNSeWFXNW5EQVFBQW1sa0EybHVkQVFDQUFJPXydzWeNAWvpu-u1XMnStU5xkOWlJsElIbf84Ry9fyQq3w=="

def setup_test_database():
    """
    Create test database with real data fetched from API using process_and_aggregate.py
    """
    # Ensure data directory exists
    os.makedirs(os.path.dirname(TEST_DB_FILE), exist_ok=True)
    
    # Remove existing test database if it exists
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)
    
    # Connect to the test database
    conn = sqlite3.connect(TEST_DB_FILE)
    
    # Process each table to fetch real data
    for table_name in SCHEMA.keys():
        try:
            print(f"Fetching real data for table: {table_name}")
            process_table(conn, table_name, SESSION_ID)
            print(f"Successfully processed table {table_name}")
        except Exception as e:
            print(f"Error fetching data for table {table_name}: {e}")
    
    # Close the connection
    conn.close()
    
    # Print statistics about the fetched data
    print("\nTest database statistics:")
    stats = get_table_stats(TEST_DB_FILE)
    print_table_stats(stats)
    
    print(f"Test database created at {TEST_DB_FILE}")

def validate_test_database():
    """Validate that the test database has data in all tables"""
    if not os.path.exists(TEST_DB_FILE):
        raise FileNotFoundError(f"Test database {TEST_DB_FILE} not found.")
        
    conn = sqlite3.connect(TEST_DB_FILE)
    c = conn.cursor()
    
    validation_results = {}
    
    for table_name in SCHEMA.keys():
        try:
            c.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = c.fetchone()[0]
            validation_results[table_name] = {
                "exists": True,
                "record_count": count,
                "has_data": count > 0
            }
        except sqlite3.OperationalError:
            validation_results[table_name] = {
                "exists": False,
                "record_count": 0,
                "has_data": False
            }
    
    conn.close()
    
    # Check if any table has no data
    missing_data = [table for table, result in validation_results.items() 
                   if not result["has_data"]]
    
    if missing_data:
        print(f"Warning: The following tables have no data: {', '.join(missing_data)}")
    
    return validation_results

if __name__ == "__main__":
    setup_test_database()
    validation = validate_test_database()
    print("\nDatabase validation results:")
    for table, result in validation.items():
        status = "✅" if result["has_data"] else "❌"
        print(f"{status} {table}: {result['record_count']} records") 