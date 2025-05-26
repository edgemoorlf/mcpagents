# mcpagents
Agent with MCP capabilities

# MCP Agents Data Processing and Query

## Data Processing

1. Place your JSON data file (e.g., `a.json`) in the `data/` directory.
2. Run the following script to process and import the data into an SQLite database:

```bash
python app/process_and_aggregate.py
```

This will create `model_stats.db` in the `data/` directory.

## Querying Statistics (MCP Methods)

Use the provided MCP methods to query statistics, such as total tokens used for a model in a time range:

```python
from app.mcp_methods import get_model_token_usage

# Example: Query for 'deepseek-r1' in the last 24 hours
import time
now = int(time.time())
one_day_ago = now - 86400
result = get_model_token_usage('deepseek-r1', one_day_ago, now)
print(result)
```

You can adapt the `get_model_token_usage` function for other models and time ranges as needed.

## Chatbox API

A web-based chatbox backend is provided using FastAPI. To run it:

```bash
uvicorn app.chat_service:app --reload
```

You can then POST questions to the `/ask` endpoint. Example using `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/ask" \
     -H "Content-Type: application/json" \
     -d '{"question": "how many tokens have been consumed for deepseek-r1?"}'
```

You can also specify a time range:

```bash
curl -X POST "http://127.0.0.1:8000/ask" \
     -H "Content-Type: application/json" \
     -d '{"question": "how many tokens have been consumed for deepseek-r1?", "start_timestamp": 1747130193, "end_timestamp": 1747220193}'
```

## Chatbox (Coming Soon)

A web-based chatbox interface will be provided to interact with MCP methods and query statistics from your data.
