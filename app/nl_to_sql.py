import sqlite3 # For type hinting and potential direct use later
from datetime import datetime
from typing import List, Tuple, Any, Optional, Dict
from app.llm_service import llm_service
from app.schema_loader import load_schema
import os

# --- LLM-based NL2SQL (Conceptual) ---

def format_chat_history_for_prompt(chat_history: List[Dict[str, str]]) -> str:
    if not chat_history:
        return "No prior conversation."
    formatted_history = "\n".join([f"{turn['role']}: {turn['content']}" for turn in chat_history])
    return f"Relevant conversation history:\n{formatted_history}"

def format_schema_for_llm(db_schema: Dict) -> str:
    """
    Formats the enriched database schema into a detailed, LLM-friendly description.
    Handles missing fields for compacted schemas.
    """
    schema_parts = []
    
    for table_name, table_info in db_schema.items():
        # Start with table description
        parts = [
            f"Table '{table_name}':",
            f"Purpose: {table_info.get('table_description', '')}",
            "\nColumns:"
        ]
        
        # Add detailed column information
        for col in table_info['columns']:
            col_desc = [
                f"  - {col['name']} ({col['type']})",
                f"    Description: {col.get('description', '')}"
            ]
            if 'constraints' in col:
                col_desc.append(f"    Constraints: {col['constraints']}")
            if 'examples' in col:
                col_desc.append(f"    Example values: {', '.join(col['examples'])}")
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

def construct_llm_prompt(question: str, chat_history: Optional[List[Dict[str, str]]], db_schema_description: str, prompt_instructions: dict) -> str:
    history_str = format_chat_history_for_prompt(chat_history) if chat_history else ""
    sql_dialect = prompt_instructions.get("sql_dialect", "SQL")
    notes = "\n".join(f"{i+1}. {n}" for i, n in enumerate(prompt_instructions.get("important_notes", [])))
    extra_notes = "\n".join(prompt_instructions.get("notes", []))
    prompt = f"""You are an AI assistant that converts natural language questions into {sql_dialect} queries.\nBased on the provided database schema, user question, and conversation history, generate a single, valid {sql_dialect} query.\nOnly output the SQL query. Do not include any explanations or markdown formatting.\n\nDatabase Schema Details:\n{db_schema_description}\n\nImportant Notes:\n{notes}\n{extra_notes}\n\nConversation History:\n{history_str}\n\nCurrent User Question: {question}\n\nSQL Query:\n"""
    return prompt

def clean_llm_sql_response(sql: str) -> str:
    if not sql:
        return ""
    sql = sql.strip()
    # Remove code block markers
    if sql.startswith("```"):
        sql = sql.strip("`")
        # Remove language identifier if present
        if sql.lower().startswith("sql"):
            sql = sql[3:].lstrip()
    # Remove leading 'SQL:' or similar
    if sql[:4].lower() == "sql:":
        sql = sql[4:].lstrip()
    return sql.strip()

def generate_sql_via_llm(question: str, chat_history: Optional[List[Dict[str, str]]], db_schema: Optional[Dict] = None, db_name: str = 'default', tables: Optional[List[str]] = None, debug: bool = False) -> Optional[str]:
    """
    Generates SQL using the LLM service. Loads schema dynamically if not provided.
    If debug is True or the environment variable NL2SQL_DEBUG is set, print prompt and LLM response.
    """
    # Load schema if not provided
    if db_schema is None:
        try:
            db_schema = load_schema(db_name=db_name, tables=tables)
        except Exception as e:
            print(f"Error loading schema for db '{db_name}': {e}")
            return None
    # Extract prompt instructions from schema
    prompt_instructions = db_schema.get('llm_prompt_instructions', {})
    # Remove llm_prompt_instructions from schema before formatting
    schema_for_llm = {k: v for k, v in db_schema.items() if k != 'llm_prompt_instructions'}
    schema_description = format_schema_for_llm(schema_for_llm)
    prompt = construct_llm_prompt(question, chat_history, schema_description, prompt_instructions)
    debug_mode = debug or os.environ.get('NL2SQL_DEBUG', '').lower() in ('1', 'true', 'yes')
    if debug_mode:
        print("\n--- LLM PROMPT (DEBUG MODE) ---\n" + prompt + "\n------------------------------")
    try:
        sql_query = llm_service.generate_completion(
            system_prompt=f"You are a SQL expert that converts natural language to {prompt_instructions.get('sql_dialect', 'SQL')} queries.",
            user_prompt=prompt
        )
        if debug_mode:
            print("\n--- LLM RAW RESPONSE (DEBUG MODE) ---\n" + str(sql_query) + "\n------------------------------")
        sql_query_clean = clean_llm_sql_response(sql_query)
        if not sql_query_clean.lower().startswith(('select', 'with')):
            print("LLM did not generate a valid SQL query")
            return None
        return sql_query_clean
    except Exception as e:
        print(f"Error generating SQL via LLM: {str(e)}")
        return None

# Only LLM-based SQL generation is now supported.
generate_sql_from_question = generate_sql_via_llm

if __name__ == '__main__':
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
        sql_llm = generate_sql_via_llm(q_llm, history, db_name='default')
        print(f"SQL (Conceptual LLM): {sql_llm}\n") 