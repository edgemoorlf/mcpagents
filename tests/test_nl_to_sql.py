import os
import sys
import sqlite3

# Ensure the parent directory is in sys.path so we can import app.nl_to_sql
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.nl_to_sql import generate_sql_from_question

data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
db_path = os.path.join(data_dir, 'model_stats.db')

def run_test(question):
    sql = generate_sql_from_question(question)
    print(f"Question: {question}")
    print(f"Generated SQL: {sql}")
    if not sql:
        print("No SQL generated.\n")
        return
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}\n")
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql)
        results = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()
        print(f"Results: {results}")
        if column_names:
            print(f"Columns: {column_names}")
        print()
    except Exception as e:
        print(f"Error executing SQL: {e}\n")

test_questions = [
    "最近的1周金额消耗、总tokens、总次数情况?",
    "最近的1天每个model调用次数分布情况?",
    "最近1天平均rpm/tpm情况?",
    "request count for claude-3-7-sonnet-20250219 from 1747130400 to 1747137600",
    "What is the quota for gpt-4o-2024-08-06?",
    "quota of o1-preview",
    "List all models.",
    "what models are there?",
    "What is the tokens for deepseek-r1 between 1747130400 and 1747134000?"
]

if __name__ == '__main__':
    for q in test_questions:
        run_test(q) 