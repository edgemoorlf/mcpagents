# Chat Service Test Suite

This directory contains automated tests for the AI model usage statistics chat service.

## Test Overview

The test suite in `test_chat_service.py` validates the natural language query capabilities of the chat service, focusing on the following use cases:

1. **Usage Statistics (model_stats table)**
   - Recent consumption, tokens, and request counts for different time periods (hour/day/week)
   - Model call distribution across different time periods
   - Average RPM (requests per minute) and TPM (tokens per minute) metrics

2. **Token Information (token table)**
   - Detailed information about existing API tokens

3. **Model & Channel Usage (log table)**
   - Total consumption, RPM, TPM for specific models in time ranges
   - Total consumption, RPM, TPM for specific channels in time ranges

4. **Channel Information (channel table)**
   - Detailed information about existing channels

5. **User Information (user table)**
   - User account information and quota usage
   - Query for specific users or comparing users
   - Analysis of quota utilization across users

## Test Data

The tests use **real data** from the production API rather than generated test data. This ensures that the tests accurately reflect the behavior of the system with actual production data.

Key points about the test data:
- Data is fetched from the API using a session ID
- It's stored in a separate test database at `data/test_model_stats.db`
- The database is created only once and reused across test runs to minimize API calls
- If any table is missing data, the database will be regenerated

## Running the Tests

To run all tests:

```bash
pytest app/test_chat_service.py -v
```

To run a specific test category:

```bash
# Run only usage statistics tests
pytest app/test_chat_service.py::test_recent_usage_stats -v

# Run only token information tests
pytest app/test_chat_service.py::test_token_info -v
```

## Test Assertions

Each test validates:

1. The API returns a successful response (status code 200)
2. The response contains an "answer" field with a string value
3. The answer contains expected information (varies by test)
4. The generated SQL query is appropriate for the question
5. The correct database table is being queried
6. Time-based queries include appropriate timestamp conditions

## Adding New Tests

To add new test cases:
1. Add individual test functions or expand the parametrized tests in `test_various_queries`
2. Ensure each test validates both the answer content and SQL correctness
3. Add appropriate assertions to check for expected information in responses

## Troubleshooting

If tests fail, check:
1. The chat service is running and accessible
2. The test database contains sufficient data (check `data/test_model_stats.db`)
3. The session ID may have expired - update it in `test_data.py` if needed
4. The natural language to SQL conversion is working properly
5. The time ranges are appropriate (tests use dynamic time calculations)

### Regenerating Test Data

If you need to regenerate the test data:

```bash
# Run the test data generator script directly
python -m app.test_data

# Or delete the test database to force regeneration on next test run
rm data/test_model_stats.db
``` 