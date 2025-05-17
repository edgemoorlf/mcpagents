import pytest
import json
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import time
import os
import sqlite3

# Import test data generator
from app.test_data import setup_test_database, TEST_DB_FILE, validate_test_database

# Import your chat service app - adjust import path as needed
from app.chat_service import app

# Initialize the test client
client = TestClient(app)

# Setup the test database before running tests
@pytest.fixture(scope="session", autouse=True)
def initialize_test_db():
    """Create test database with real data before running tests"""
    print("Setting up test database with real data from API...")
    
    # Check if test database already exists
    if not os.path.exists(TEST_DB_FILE):
        setup_test_database()
    else:
        print(f"Test database {TEST_DB_FILE} already exists, validating...")
        validation = validate_test_database()
        missing_data = [table for table, result in validation.items() 
                       if not result["has_data"]]
        
        # If any table is missing data, recreate the database
        if missing_data:
            print(f"Missing data in tables: {', '.join(missing_data)}")
            print("Recreating test database...")
            setup_test_database()
    
    # Point the app to use the test database 
    # Note: You may need to adjust this based on how your app loads the database path
    from app import chat_service
    chat_service.DB_FILE = TEST_DB_FILE
    
    # Make sure the database exists and has data
    assert os.path.exists(TEST_DB_FILE), f"Test database {TEST_DB_FILE} was not created"
    
    # Quick validation that data exists
    conn = sqlite3.connect(TEST_DB_FILE)
    c = conn.cursor()
    
    # Check all tables have data
    all_valid = True
    for table_name in ["model_stats", "pricing", "token", "log", "channel"]:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = c.fetchone()[0]
            if count == 0:
                all_valid = False
                print(f"Table {table_name} has no data!")
        except sqlite3.OperationalError:
            all_valid = False
            print(f"Table {table_name} doesn't exist!")
    
    conn.close()
    
    if not all_valid:
        pytest.skip("Test database is not correctly setup with all required data")
    
    yield  # This allows the tests to run
    
    # We don't clean up the test database after tests since it contains real data
    # that we might want to reuse to avoid making API calls every test run

# Helper function to get timestamp for different time periods
def get_time_range(period):
    now = int(time.time())
    if period == "hour":
        start = now - 3600
    elif period == "day":
        start = now - 86400
    elif period == "week":
        start = now - 604800
    else:
        raise ValueError(f"Unsupported period: {period}")
    return start, now

# Test case 1: Usage statistics for different time periods
@pytest.mark.parametrize("period", ["hour", "day", "week"])
def test_recent_usage_stats(period):
    """测试最近的1小时/1天/1周金额消耗、总tokens、总次数情况"""
    query = f"最近{period}的金额消耗、总tokens、总次数情况"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check that the response contains expected information
    answer = data["answer"]
    assert "消耗" in answer or "quota" in answer
    assert "tokens" in answer or "令牌" in answer
    assert "次数" in answer or "count" in answer
    
    # Verify that SQL was correctly generated
    assert "sql" in data
    assert "model_stats" in data["sql"]
    assert "SUM" in data["sql"]
    
    # Time range check
    start, end = get_time_range(period)
    # Check that timestamps are used in the query
    assert str(start) in data["sql"] or str(end) in data["sql"]

# Test case 2: Model call distribution for different time periods
@pytest.mark.parametrize("period", ["hour", "day", "week"])
def test_model_call_distribution(period):
    """测试最近的1小时/1天/1周每个model调用次数分布情况"""
    query = f"最近{period}每个model调用次数分布情况"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check response contains model distribution information
    answer = data["answer"]
    assert "model" in answer.lower() or "模型" in answer
    assert "次数" in answer or "count" in answer
    
    # Verify SQL includes correct grouping
    assert "sql" in data
    assert "model_stats" in data["sql"]
    assert "GROUP BY model_name" in data["sql"]
    
    # Time range check
    start, end = get_time_range(period)
    assert str(start) in data["sql"] or str(end) in data["sql"]

# Test case 3: Average RPM/TPM for different time periods
@pytest.mark.parametrize("period", ["hour", "day", "week"])
def test_average_rpm_tpm(period):
    """测试最近的1小时/1天/1周平均rpm/tpm情况"""
    query = f"最近{period}平均rpm和tpm情况"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check that response includes RPM/TPM information
    answer = data["answer"]
    assert "rpm" in answer.lower() or "requests per minute" in answer.lower()
    assert "tpm" in answer.lower() or "tokens per minute" in answer.lower()
    
    # Verify SQL calculation is correct for RPM/TPM
    assert "sql" in data
    assert "model_stats" in data["sql"]
    assert "AVG" in data["sql"] or "SUM" in data["sql"]
    
    # Time range check
    start, end = get_time_range(period)
    assert str(start) in data["sql"] or str(end) in data["sql"]

# Test case 4: Token information
def test_token_info():
    """测试现有令牌具体信息"""
    query = "现有令牌具体信息"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check response includes token information
    answer = data["answer"]
    assert "令牌" in answer or "token" in answer.lower()
    
    # Verify correct table is used
    assert "sql" in data
    assert "token" in data["sql"]

# Test case 5: Model usage in specific time range
def test_model_specific_time_range():
    """测试某一个模型在某段时间范围内的总消耗、rpm、tpm情况"""
    # Get one week time range for this test
    start, end = get_time_range("week")
    start_date = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
    end_date = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
    
    query = f"gpt-4o在{start_date}到{end_date}的总消耗、rpm、tpm情况"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check that response includes model and metrics
    answer = data["answer"]
    assert "gpt-4o" in answer
    assert "消耗" in answer or "quota" in answer or "cost" in answer.lower()
    assert "rpm" in answer.lower() or "tpm" in answer.lower()
    
    # Verify SQL uses log table and includes model name
    assert "sql" in data
    assert "log" in data["sql"]
    assert "gpt-4o" in data["sql"]
    assert f"{start}" in data["sql"] or f"{end}" in data["sql"] or start_date in data["sql"] or end_date in data["sql"]

# Test case 6: Channel usage in specific time range
def test_channel_specific_time_range():
    """测试某一个渠道在某段时间范围内的总消耗、rpm、tpm情况"""
    # Get one week time range for this test
    start, end = get_time_range("week")
    start_date = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
    end_date = datetime.fromtimestamp(end).strftime("%Y-%m-%d")
    
    query = f"渠道'zmnz-gpt-all'在{start_date}到{end_date}的总消耗、rpm、tpm情况"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check that response includes channel and metrics
    answer = data["answer"]
    assert "zmnz-gpt-all" in answer
    assert "消耗" in answer or "quota" in answer or "cost" in answer.lower()
    assert "rpm" in answer.lower() or "tpm" in answer.lower()
    
    # Verify SQL uses log table and includes channel info
    assert "sql" in data
    assert "log" in data["sql"]
    assert "zmnz-gpt-all" in data["sql"] or "channel_name" in data["sql"]
    assert f"{start}" in data["sql"] or f"{end}" in data["sql"] or start_date in data["sql"] or end_date in data["sql"]

# Test case 7: Channel information
def test_channel_info():
    """测试现有渠道具体信息"""
    query = "现有渠道具体信息"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check response includes channel information
    answer = data["answer"]
    assert "渠道" in answer or "channel" in answer.lower()
    
    # Verify correct table is used
    assert "sql" in data
    assert "channel" in data["sql"]

# Test case 8: User information
def test_user_info():
    """测试用户账户信息"""
    query = "所有用户的账户信息和配额使用情况"
    response = client.post("/chat", json={"query": query})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    
    # Check response includes user information
    answer = data["answer"]
    assert "用户" in answer or "user" in answer.lower()
    assert "配额" in answer or "quota" in answer.lower()
    
    # Verify correct table is used
    assert "sql" in data
    assert "user" in data["sql"]

# Run multiple test cases with more specific variations
@pytest.mark.parametrize("test_case", [
    "最近1小时deepseek-r1的使用量和消耗",
    "今天gpt-4o和claude-3消耗对比",
    "本周每日token使用趋势",
    "查询名为'aliyun'的token的剩余额度",
    "哪个渠道的响应时间最快",
    "上周每个模型的平均tokens",
    "哪个用户的配额使用最多",
    "用户'aliyun'的配额使用比例是多少"
])
def test_various_queries(test_case):
    """测试各种不同的查询变体"""
    response = client.post("/chat", json={"query": test_case})
    
    assert response.status_code == 200
    data = response.json()
    
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert "sql" in data
    
    # The query should have generated valid SQL
    assert len(data["sql"]) > 10
    assert "SELECT" in data["sql"] 