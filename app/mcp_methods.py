import sqlite3
from datetime import datetime

DB_FILE = '../data/model_stats.db'

def get_model_token_usage(model_name: str, start_timestamp: int, end_timestamp: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT SUM(token_used) as total_tokens, SUM(count) as total_count
        FROM model_stats
        WHERE model_name = ? AND created_at BETWEEN ? AND ?
    ''', (model_name, start_timestamp, end_timestamp))
    row = c.fetchone()
    conn.close()
    return {
        'model_name': model_name,
        'total_tokens': row[0] or 0,
        'total_count': row[1] or 0,
        'time_range': {
            'start': start_timestamp,
            'end': end_timestamp
        }
    }

# Example usage:
if __name__ == '__main__':
    # Example: deepseek r1, last 24 hours
    model = 'deepseek-r1'
    now = int(datetime.now().timestamp())
    one_day_ago = now - 86400
    result = get_model_token_usage(model, one_day_ago, now)
    print(result) 