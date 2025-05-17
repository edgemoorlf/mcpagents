import re
import sqlite3 # For type hinting and potential direct use later
from datetime import datetime
from typing import List, Tuple, Any, Optional, Dict
from app.llm_service import llm_service
from app.process_and_aggregate import export_schema_for_nl2sql

# Get the schema from process_and_aggregate.py 
TABLE_SCHEMA = export_schema_for_nl2sql()

# Define a mapping of natural language patterns to SQL query builders
# Each key is a regex, and each value is a function that takes match groups and returns SQL
# Order matters: more specific patterns should come before general ones.

def build_sum_query(match_groups: Tuple[str, ...], column: str) -> str:
    # The first element in match_groups for these patterns is the model name.
    # If time range is present, match_groups will have model_name, start_time, end_time
    model_name = match_groups[0]
    # Check if time range parameters are provided and are not None
    if len(match_groups) == 3 and match_groups[1] is not None and match_groups[2] is not None: # with time range
        start_time, end_time = match_groups[1], match_groups[2]
        return f"SELECT SUM({column}) FROM model_stats WHERE model_name = '{model_name}' AND created_at BETWEEN {start_time} AND {end_time};"
    return f"SELECT SUM({column}) FROM model_stats WHERE model_name = '{model_name}';"

def build_list_query(match_groups: Tuple[str, ...], column: str) -> str:
    if len(match_groups) > 0 and match_groups[0]: # specific model
        model_name = match_groups[0]
        return f"SELECT {column} FROM model_stats WHERE model_name = '{model_name}' ORDER BY created_at DESC LIMIT 10;" # Example: last 10 records for a model
    return f"SELECT DISTINCT {column} FROM model_stats;"


NL_TO_SQL_PATTERNS = [
    # Token usage: "how many tokens for X [between A and B]" or "tokens used by X [from A to B]"
    (re.compile(r"how many tokens .* for ([^\s?]+)(?: between (\d+) and (\d+))?\??", re.I),
     lambda mg: build_sum_query(mg, "token_used")),
    (re.compile(r"tokens used by ([^\s?]+)(?: from (\d+) to (\d+))?\??", re.I),
     lambda mg: build_sum_query(mg, "token_used")),

    # Count / Requests: "how many requests for X [between A and B]" or "request count for X [from A to B]"
    (re.compile(r"how many requests .* for ([^\s?]+)(?: between (\d+) and (\d+))?\??", re.I),
     lambda mg: build_sum_query(mg, "count")),
    (re.compile(r"request count for ([^\s?]+)(?: from (\d+) to (\d+))?\??", re.I),
     lambda mg: build_sum_query(mg, "count")),

    # Quota: "what is the quota for X" or "quota of X"
    (re.compile(r"what is the quota for ([^\s?]+)\??", re.I),
     lambda mg: f"SELECT quota FROM model_stats WHERE model_name = '{mg[0]}' ORDER BY created_at DESC LIMIT 1;"),
    (re.compile(r"quota of ([^\s?]+)\??", re.I),
     lambda mg: f"SELECT quota FROM model_stats WHERE model_name = '{mg[0]}' ORDER BY created_at DESC LIMIT 1;"),

    # List models: "list all models" or "what models are there"
    (re.compile(r"list all models\??", re.I),
     lambda mg: "SELECT DISTINCT model_name FROM model_stats;"),
    (re.compile(r"what models are there\??", re.I),
     lambda mg: "SELECT DISTINCT model_name FROM model_stats;"),

    # Generic "what is the X for Y [between A and B]"
    # The model name is group 1, optional start_time is group 2, optional end_time is group 3
    # The target column (tokens/requests) is group 0
    (re.compile(r"what is the (tokens|token_used|requests|count) for ([^\s?]+)(?: between (\d+) and (\d+))?\??", re.I),
     lambda mg: build_sum_query( (mg[1], mg[2], mg[3]) , "token_used" if mg[0] in ["tokens", "token_used"] else "count")),
]

def generate_sql_from_question_regex(question: str) -> Optional[str]:
    """
    Tries to convert a natural language question into an SQL query
    based on predefined patterns.
    """
    question_cleaned = question.strip() # Keep case for model names if needed, but patterns are case-insensitive
    for pattern, query_builder_func in NL_TO_SQL_PATTERNS:
        match = pattern.match(question_cleaned)
        if match:
            try:
                # Pass only the captured groups to the builder
                sql = query_builder_func(match.groups())
                # Basic validation
                if sql and "select " in sql.lower() and "from model_stats" in sql.lower():
                    return sql
            except Exception as e:
                print(f"Error building SQL (regex) for pattern {pattern.pattern} with groups {match.groups()}: {e}")
                continue
    return None

# --- LLM-based NL2SQL (Conceptual) ---

def format_chat_history_for_prompt(chat_history: List[Dict[str, str]]) -> str:
    if not chat_history:
        return "No prior conversation."
    formatted_history = "\n".join([f"{turn['role']}: {turn['content']}" for turn in chat_history])
    return f"Relevant conversation history:\n{formatted_history}"

def format_schema_for_llm(db_schema: Dict) -> str:
    """
    Formats the enriched database schema into a detailed, LLM-friendly description.
    """
    schema_parts = []
    
    for table_name, table_info in db_schema.items():
        # Start with table description
        parts = [
            f"Table '{table_name}':",
            f"Purpose: {table_info['table_description']}",
            "\nColumns:"
        ]
        
        # Add detailed column information
        for col in table_info['columns']:
            col_desc = [
                f"  - {col['name']} ({col['type']})",
                f"    Description: {col['description']}",
                f"    Constraints: {col['constraints']}",
                f"    Example values: {', '.join(col['examples'])}"
            ]
            if 'usage' in col:
                col_desc.append(f"    Usage: {col['usage']}")
            if 'aggregation' in col:
                col_desc.append(f"    Typical aggregation: {col['aggregation']}")
            parts.extend(col_desc)
        
        # Add value ranges
        if 'value_ranges' in table_info:
            parts.append("\nTypical value ranges:")
            for field, range_desc in table_info['value_ranges'].items():
                parts.append(f"  - {field}: {range_desc}")
        
        # Add common query patterns
        if 'common_queries' in table_info:
            parts.append("\nCommon query patterns:")
            for query in table_info['common_queries']:
                parts.append(f"  - {query}")
        
        # Add time series nature if present
        if 'time_series_nature' in table_info:
            parts.append(f"\nTime series characteristics: {table_info['time_series_nature']}")
        
        schema_parts.extend(parts)
    
    return "\n".join(schema_parts)

def construct_llm_prompt(question: str, chat_history: Optional[List[Dict[str, str]]], db_schema_description: str) -> str:
    history_str = format_chat_history_for_prompt(chat_history) if chat_history else ""
    
    prompt = f"""You are an AI assistant that converts natural language questions into SQLite SQL queries.
Based on the provided database schema, user question, and conversation history, generate a single, valid SQLite query.
Only output the SQL query. Do not include any explanations or markdown formatting.

Database Schema Details:
{db_schema_description}

Important Notes:
1. The data is time-series based, so consider time ranges from the conversation history.
2. Model names are case-sensitive.
3. All numeric columns (token_used, count, quota) should be >= 0.
4. When querying time ranges, use the created_at column with BETWEEN clause.
5. For aggregations, consider using SUM, AVG, or COUNT as appropriate.
6. The current time is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, so if the user's question does not mention the year or month, use the current year and month.
7. Vendor(供应商) is the name of the company that provides the model. It is a prefix of the channel name. So please use the vendor name to query the channel name with LIKE operator.

Conversation History:
{history_str}

Current User Question: {question}

SQL Query:
"""
    return prompt

def generate_sql_via_llm(question: str, chat_history: Optional[List[Dict[str, str]]], db_schema: Dict) -> Optional[str]:
    """
    Generates SQL using the LLM service.
    """
    # Format the enriched schema for the LLM
    schema_description = format_schema_for_llm(db_schema)
    
    # Construct the prompt with the formatted schema
    prompt = construct_llm_prompt(question, chat_history, schema_description)
    print(f"--- LLM PROMPT ---\n{prompt}\n------------------------------")
    
    try:
        # Use the LLM service to generate SQL
        sql_query = llm_service.generate_completion(
            system_prompt="You are a SQL expert that converts natural language to SQLite queries.",
            user_prompt=prompt
        )
        
        # Basic validation - ensure it's a SQL query
        if not sql_query or not sql_query.lower().startswith(('select', 'with')):
            print("LLM did not generate a valid SQL query")
            return None
            
        return sql_query
        
    except Exception as e:
        print(f"Error generating SQL via LLM: {str(e)}")
        return None

# Renaming the original function to avoid confusion
generate_sql_from_question = generate_sql_from_question_regex

if __name__ == '__main__':
    # Test Regex-based
    print("--- TESTING REGEX-BASED ---")
    test_questions_regex = [
        "How many tokens were consumed for deepseek-r1?",
        "List all models."
    ]
    for q in test_questions_regex:
        sql = generate_sql_from_question_regex(q)
        print(f"Q: {q}\nSQL (Regex): {sql}\n")

    # Test Conceptual LLM-based
    print("\n--- TESTING CONCEPTUAL LLM-BASED ---")
    sample_history_with_time = [
        {"role": "user", "content": "What was the usage from yesterday to today?"},
        {"role": "assistant", "content": "I can look that up. For which model?"}
    ]
    test_questions_llm = [
        ("how many tokens consumed for deepseek-r1?", sample_history_with_time),
        ("What is the total count for gpt-4o?", None) # No history
    ]
    for q_llm, history in test_questions_llm:
        print(f"Testing LLM with Q: {q_llm}")
        sql_llm = generate_sql_via_llm(q_llm, history, TABLE_SCHEMA)
        print(f"SQL (Conceptual LLM): {sql_llm}\n") 