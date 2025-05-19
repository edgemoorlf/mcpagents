import sqlite3
import os
import json
import argparse
import requests
from datetime import datetime
from typing import Dict, List, Tuple, Any, Optional

# Base configuration 
BASE_URL = 'https://api.zhimiaonengzhi.com/api'
DB_FILE = 'data/model_stats.db'

# Headers used for all API requests
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Cache-Control': 'no-store',
    'Connection': 'keep-alive',
    'New-API-User': '1',
    'Pragma': 'no-cache',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
}

# Define the schema and metadata for all tables
# This combines both structural info for table creation and metadata for NL queries
SCHEMA = {
    "model_stats": {
        "endpoint": "/data/",
        "params": {
            "username": "",
            "default_time": "hour",
            # start_timestamp and end_timestamp added at runtime
        },
        "response_key": "data",  # Where in the JSON response to find the data
        "columns": [
            {
                "name": "model_name",
                "type": "TEXT",
                "description": "The identifier of the AI model (e.g., 'deepseek-r1', 'gpt-4o')",
                "examples": ["deepseek-r1", "gpt-4o", "claude-3-7-sonnet-20250219"],
                "constraints": "Non-null, case-sensitive"
            },
            {
                "name": "created_at",
                "type": "INTEGER",
                "description": "Unix timestamp (in seconds) when these statistics were recorded",
                "examples": ["1747130400", "1747134000"],
                "constraints": "Non-null, >= 0",
                "usage": "Used in time range queries like 'between timestamp1 AND timestamp2'"
            },
            {
                "name": "token_used",
                "type": "INTEGER",
                "description": "Tokens processed by this model in this time period",
                "examples": ["52889467", "6263428"],
                "constraints": "Non-null, >= 0",
                "aggregation": "Often summed over time periods to show total usage"
            },
            {
                "name": "count",
                "type": "INTEGER",
                "description": "Number of requests/API calls to this model in one hour(3600 seconds)",
                "examples": ["19228", "4304"],
                "constraints": "Non-null, >= 0",
                "aggregation": "Often summed to show total request count"
            },
            {
                "name": "quota",
                "type": "INTEGER",
                "description": "The cost in quota units (divide by 500000 for USD)",
                "examples": ["69189649", "9496154"],
                "constraints": "Non-null, >= 0",
                "usage": "Often summed to show total cost"
            }
        ],
        "table_description": "Stores usage statistics and cost information for various AI language models over time. Each record represents a model's usage metrics in 3600 seconds. Queries for rpm (requests per minute) and tpm (tokensper minute) should be based the data on this table, divided by 60.",
        "time_series_nature": "Data is time-series with created_at timestamps. Queries often involve time ranges and aggregations.",
        "common_queries": [
            "Sum of tokens used by a specific model in a time range",
            "Total request count for a model",
            "Latest quota for a model",
            "List of all unique model names",
            "Usage trends over time"
        ],
        "value_ranges": {
            "token_used": "Typically ranges from thousands to millions",
            "count": "Typically ranges from single digits to tens of thousands",
            "quota": "Typically ranges from millions to billions"
        }
    },
    "pricing": {
        "endpoint": "/pricing",
        "params": {},
        "response_key": "data",
        "columns": [
            {
                "name": "model_name",
                "type": "TEXT",
                "description": "The identifier of the AI model",
                "examples": ["gpt-4o", "deepseek-v3"],
                "constraints": "Non-null, case-sensitive"
            },
            {
                "name": "quota_type",
                "type": "INTEGER",
                "description": "Type of quota allocation for this model",
                "examples": ["0", "1"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "model_ratio",
                "type": "REAL",
                "description": "Pricing ratio for this model relative to base models",
                "examples": ["0.625", "37.5"],
                "constraints": "Non-null, >= 0",
                "usage": "Higher values indicate more expensive models"
            },
            {
                "name": "model_price",
                "type": "REAL",
                "description": "Direct price for this model if applicable",
                "examples": ["0", "1.5"],
                "constraints": ">= 0"
            },
            {
                "name": "owner_by",
                "type": "TEXT",
                "description": "Entity that owns this model",
                "examples": ["", "openai"],
                "constraints": "Can be empty"
            },
            {
                "name": "completion_ratio",
                "type": "INTEGER",
                "description": "Ratio for completion tokens compared to prompt tokens",
                "examples": ["1", "4"],
                "constraints": "Non-null, >= 1",
                "usage": "For calculating the cost of completion tokens"
            },
            {
                "name": "enable_groups",
                "type": "TEXT",
                "description": "JSON array of groups that can use this model",
                "examples": ["[\"default\"]", "[\"admin\",\"premium\"]"],
                "constraints": "Non-null, stored as JSON string"
            }
        ],
        "table_description": "Contains pricing and availability information for different AI models. Each record represents a model's pricing structure and which user groups can access it.",
        "common_queries": [
            "Most expensive models by model_ratio",
            "Models available to specific user groups",
            "Models with special completion pricing"
        ]
    },
    "token": {
        "endpoint": "/token/",
        "params": {
            "p": 0,
            "size": 100  # Increased size to get more data in one request
        },
        "response_key": "data",
        "columns": [
            {
                "name": "id",
                "type": "INTEGER",
                "description": "Unique identifier for the token record",
                "examples": ["1", "42"],
                "constraints": "Non-null, primary key"
            },
            {
                "name": "user_id",
                "type": "INTEGER",
                "description": "ID of the user who owns this token",
                "examples": ["101", "505"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "key",
                "type": "TEXT",
                "description": "The token string used for API authentication",
                "examples": ["Rn4Psd4qKlH29k6XqGMJvt14gYx5dXkLdeZInau2BEDKkT1H"],
                "constraints": "Non-null, unique"
            },
            {
                "name": "status",
                "type": "INTEGER",
                "description": "Status flag for the token (e.g., 1=active, 0=inactive)",
                "examples": ["1", "0"],
                "constraints": "Non-null, 0 or 1"
            },
            {
                "name": "name",
                "type": "TEXT",
                "description": "Name or identifier for this token",
                "examples": ["test", "root"],
                "constraints": "Non-null"
            },
            {
                "name": "created_time",
                "type": "INTEGER",
                "description": "Unix timestamp when the token was created",
                "examples": ["1741854716", "1741012223"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "accessed_time",
                "type": "INTEGER",
                "description": "Unix timestamp when the token was last accessed",
                "examples": ["1745387920", "1747115590"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "expired_time",
                "type": "INTEGER",
                "description": "Unix timestamp when the token expires (-1 = never)",
                "examples": ["-1", "1758000000"],
                "constraints": "Non-null"
            },
            {
                "name": "remain_quota",
                "type": "INTEGER",
                "description": "Remaining quota for this token",
                "examples": ["958994", "70426382"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "unlimited_quota",
                "type": "INTEGER",
                "description": "Whether this token has unlimited quota (0=false, 1=true)",
                "examples": ["0", "1"],
                "constraints": "Non-null, 0 or 1"
            },
            {
                "name": "model_limits_enabled",
                "type": "INTEGER",
                "description": "Whether model limits are enabled for this token (0=false, 1=true)",
                "examples": ["0", "1"],
                "constraints": "Non-null, 0 or 1"
            },
            {
                "name": "model_limits",
                "type": "TEXT",
                "description": "List of models that this token is limited to",
                "examples": ["", "gpt-4,gpt-3.5-turbo"],
                "constraints": "Can be empty"
            },
            {
                "name": "allow_ips",
                "type": "TEXT",
                "description": "Comma-separated list of allowed IPs for this token",
                "examples": ["", "192.168.1.1,10.0.0.1"],
                "constraints": "Can be empty"
            },
            {
                "name": "used_quota",
                "type": "INTEGER",
                "description": "Amount of quota used by this token",
                "examples": ["58605", "29573618"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "user_group",
                "type": "TEXT",
                "description": "User group for this token",
                "examples": ["", "default"],
                "constraints": "Can be empty"
            },
            {
                "name": "DeletedAt",
                "type": "TEXT",
                "description": "Timestamp when this token was deleted (null if not deleted)",
                "examples": ["null", "2023-05-01T12:34:56Z"],
                "constraints": "Can be null"
            }
        ],
        "table_description": "Contains API token details including usage statistics, quotas, and access controls",
        "common_queries": [
            "Active tokens with remaining quota",
            "Recently used tokens",
            "Tokens with unlimited quota",
            "Tokens for specific user groups",
            "Tokens with highest usage"
        ]
    },
    # "log": {
    #     "endpoint": "/log/",
    #     "params": {
    #         "p": 1,
    #         "page_size": 1000,
    #         "type": 0,
    #         "username": "",
    #         "token_name": "",
    #         "model_name": "",
    #         "channel": "",
    #         "group": ""
    #         # start_timestamp and end_timestamp added at runtime
    #     },
    #     "response_key": "data.items",  # Note nested path to access items array
    #     "columns": [
    #         {
    #             "name": "id",
    #             "type": "INTEGER",
    #             "description": "Unique identifier for the log entry",
    #             "examples": ["144789993", "144789992"],
    #             "constraints": "Non-null, primary key"
    #         },
    #         {
    #             "name": "user_id",
    #             "type": "INTEGER",
    #             "description": "ID of the user who made the API call",
    #             "examples": ["2", "101"],
    #             "constraints": "Non-null, >= 0"
    #         },
    #         {
    #             "name": "created_at",
    #             "type": "INTEGER",
    #             "description": "Unix timestamp when the log entry was created",
    #             "examples": ["1747214216", "1747214215"],
    #             "constraints": "Non-null, >= 0",
    #             "usage": "Used for filtering logs by time period"
    #         },
    #         {
    #             "name": "type",
    #             "type": "INTEGER",
    #             "description": "Type of log entry (e.g., 2=model usage)",
    #             "examples": ["2", "1"],
    #             "constraints": "Non-null, >= 0"
    #         },
    #         {
    #             "name": "content",
    #             "type": "TEXT",
    #             "description": "Human-readable description of the log entry",
    #             "examples": ["模型倍率 1.25，补全倍率 4.00，分组倍率 1.00"],
    #             "constraints": "Can be empty"
    #         },
    #         {
    #             "name": "username",
    #             "type": "TEXT",
    #             "description": "Username of the account that made the API call",
    #             "examples": ["aliyun", "admin"],
    #             "constraints": "Non-null"
    #         },
    #         {
    #             "name": "token_name",
    #             "type": "TEXT",
    #             "description": "Name of the token used for this API call",
    #             "examples": ["aliyun-1", "aliyun"],
    #             "constraints": "Non-null"
    #         },
    #         {
    #             "name": "model_name",
    #             "type": "TEXT",
    #             "description": "Name of the AI model used",
    #             "examples": ["gpt-4o", "deepseek-r1", "gpt-4o-mini"],
    #             "constraints": "Non-null",
    #             "usage": "Used for filtering usage by model"
    #         },
    #         {
    #             "name": "quota",
    #             "type": "INTEGER",
    #             "description": "Quota cost for this API call",
    #             "examples": ["3265", "14584"],
    #             "constraints": "Non-null, >= 0",
    #             "aggregation": "Often summed to show total cost"
    #         },
    #         {
    #             "name": "prompt_tokens",
    #             "type": "INTEGER",
    #             "description": "Number of tokens in the prompt/input",
    #             "examples": ["1884", "876"],
    #             "constraints": "Non-null, >= 0",
    #             "aggregation": "Often summed to show total input tokens"
    #         },
    #         {
    #             "name": "completion_tokens",
    #             "type": "INTEGER",
    #             "description": "Number of tokens in the completion/output",
    #             "examples": ["182", "13039"],
    #             "constraints": "Non-null, >= 0",
    #             "aggregation": "Often summed to show total output tokens"
    #         },
    #         {
    #             "name": "use_time",
    #             "type": "INTEGER",
    #             "description": "Time taken to process this request in seconds",
    #             "examples": ["10", "436"],
    #             "constraints": "Non-null, >= 0",
    #             "aggregation": "Often averaged to show performance"
    #         },
    #         {
    #             "name": "is_stream",
    #             "type": "INTEGER",
    #             "description": "Whether the request used streaming (0=false, 1=true)",
    #             "examples": ["0", "1"],
    #             "constraints": "Non-null, 0 or 1",
    #             "usage": "Used to distinguish between streaming and non-streaming requests"
    #         },
    #         {
    #             "name": "channel",
    #             "type": "INTEGER",
    #             "description": "Channel ID used for this request",
    #             "examples": ["2", "56", "51"],
    #             "constraints": "Non-null, >= 0"
    #         },
    #         {
    #             "name": "channel_name",
    #             "type": "TEXT",
    #             "description": "Descriptive name of the channel used",
    #             "examples": ["ubang-oai", "腾讯-混元-dp", "清风阁-gemini"],
    #             "constraints": "Non-null"
    #         },
    #         {
    #             "name": "token_id",
    #             "type": "INTEGER",
    #             "description": "ID of the token used for this request",
    #             "examples": ["4", "2"],
    #             "constraints": "Non-null, >= 0"
    #         },
    #         {
    #             "name": "user_group",
    #             "type": "TEXT",
    #             "description": "User group for this request",
    #             "examples": ["default", "vip"],
    #             "constraints": "Non-null"
    #         },
    #         {
    #             "name": "other",
    #             "type": "TEXT",
    #             "description": "JSON string containing additional metadata",
    #             "examples": ["{\"admin_info\":{...},\"cache_ratio\":0.5,...}"],
    #             "constraints": "Can be empty",
    #             "usage": "Contains detailed pricing info and routing data"
    #         }
    #     ],
    #     "table_description": "Contains detailed logs of all AI model API calls including tokens used, processing time, cost, and routing information",
    #     "time_series_nature": "Data is time-series with created_at timestamps. Queries often involve time ranges and aggregations.",
    #     "common_queries": [
    #         "API calls by a specific user or token",
    #         "Usage statistics for a particular model",
    #         "Average response time by model or channel",
    #         "Cost breakdown by model, user, or time period",
    #         "Token usage patterns over time"
    #     ],
    #     "value_ranges": {
    #         "quota": "Typically ranges from single digits to hundreds of thousands",
    #         "prompt_tokens": "Typically ranges from tens to thousands",
    #         "completion_tokens": "Typically ranges from single digits to tens of thousands",
    #         "use_time": "Typically ranges from 1 to 500 seconds"
    #     }
    # },
    "channel": {
        "endpoint": "/channel/",
        "params": {
            "p": 0,
            "page_size": 100,
            "id_sort": "false",
            "tag_mode": "false"
        },
        "response_key": "data",
        "columns": [
            {
                "name": "id",
                "type": "INTEGER",
                "description": "Unique identifier for the channel",
                "examples": ["58", "53", "42"],
                "constraints": "Non-null, primary key"
            },
            {
                "name": "type",
                "type": "INTEGER",
                "description": "Type of the channel (e.g., 1=OpenAI API, 8=Doubao API, etc.)",
                "examples": ["1", "14", "45"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "key",
                "type": "TEXT",
                "description": "API key for the channel (typically redacted)",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "openai_organization",
                "type": "TEXT",
                "description": "OpenAI organization ID (if applicable)",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "test_model",
                "type": "TEXT",
                "description": "Model used for testing the channel",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "status",
                "type": "INTEGER",
                "description": "Status of the channel (1=active, 2=inactive, etc.)",
                "examples": ["1", "2"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "name",
                "type": "TEXT",
                "description": "Human-readable name of the channel",
                "examples": ["zmnz-gpt-all", "清风阁-grok", "上饶-claude"],
                "constraints": "Non-null"
            },
            {
                "name": "weight",
                "type": "INTEGER",
                "description": "Weight for load balancing (higher = more traffic)",
                "examples": ["0", "7", "20"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "created_time",
                "type": "INTEGER",
                "description": "Unix timestamp when the channel was created",
                "examples": ["1745747749", "1744169253"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "test_time",
                "type": "INTEGER",
                "description": "Unix timestamp of the most recent test",
                "examples": ["1747049925", "1747211854"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "response_time",
                "type": "INTEGER",
                "description": "Response time in milliseconds from the most recent test",
                "examples": ["545", "15675", "85"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "base_url",
                "type": "TEXT",
                "description": "Base URL for API requests to this channel",
                "examples": ["http://45.78.213.255", "http://38.12.5.107:3009"],
                "constraints": "Can be empty"
            },
            {
                "name": "other",
                "type": "TEXT",
                "description": "Miscellaneous information about the channel",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "balance",
                "type": "INTEGER",
                "description": "Remaining balance on the channel",
                "examples": ["0"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "balance_updated_time",
                "type": "INTEGER",
                "description": "Unix timestamp when the balance was last updated",
                "examples": ["0"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "models",
                "type": "TEXT",
                "description": "Comma-separated list of models available on this channel",
                "examples": ["gpt-4.5-preview,chatgpt-4o-latest", "deepseek-r1,deepseek-r1-250120"],
                "constraints": "Non-null"
            },
            {
                "name": "user_group",
                "type": "TEXT",
                "description": "User group that can access this channel",
                "examples": ["default"],
                "constraints": "Non-null"
            },
            {
                "name": "used_quota",
                "type": "INTEGER",
                "description": "Total quota consumed by this channel",
                "examples": ["114816436", "184953123174"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "model_mapping",
                "type": "TEXT",
                "description": "JSON mapping of model aliases to actual models",
                "examples": ["", "{\n  \"deepseek-r1\": \"deepseek-r1-250120\"\n}"],
                "constraints": "Can be empty"
            },
            {
                "name": "status_code_mapping",
                "type": "TEXT",
                "description": "JSON mapping of status codes",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "priority",
                "type": "INTEGER",
                "description": "Priority of the channel in routing decisions",
                "examples": ["100", "0"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "auto_ban",
                "type": "INTEGER",
                "description": "Whether the channel is automatically banned on failure (0=no, 1=yes)",
                "examples": ["0", "1"],
                "constraints": "Non-null, 0 or 1"
            },
            {
                "name": "other_info",
                "type": "TEXT",
                "description": "Additional information about the channel",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "tag",
                "type": "TEXT",
                "description": "Tag for categorizing the channel",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "setting",
                "type": "TEXT",
                "description": "Channel-specific settings in JSON format",
                "examples": ["", "null"],
                "constraints": "Can be null or empty"
            },
            {
                "name": "param_override",
                "type": "TEXT",
                "description": "Parameter overrides in JSON format",
                "examples": ["null"],
                "constraints": "Can be null or empty"
            }
        ],
        "table_description": "Contains information about API channels used for routing requests to various model providers",
        "common_queries": [
            "Channels by response time",
            "Active vs inactive channels",
            "Channels supporting specific models",
            "Channels with highest quota usage"
        ],
        "value_ranges": {
            "response_time": "Typically ranges from tens to thousands of milliseconds",
            "used_quota": "Typically ranges from millions to billions"
        }
    },
    "user": {
        "endpoint": "/user/",
        "params": {
            "p": 0,
            "page_size": 10
        },
        "response_key": "data.items",
        "columns": [
            {
                "name": "id",
                "type": "INTEGER",
                "description": "Unique identifier for the user account",
                "examples": ["1", "2"],
                "constraints": "Non-null, primary key"
            },
            {
                "name": "username",
                "type": "TEXT",
                "description": "Username for login (account name)",
                "examples": ["aliyun", "root"],
                "constraints": "Non-null, unique"
            },
            {
                "name": "password",
                "type": "TEXT",
                "description": "Password hash (typically empty in API response)",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "display_name",
                "type": "TEXT",
                "description": "Human-readable display name",
                "examples": ["阿里云", "Root User"],
                "constraints": "Non-null"
            },
            {
                "name": "user_role",
                "type": "INTEGER",
                "description": "User role/permission level (100=admin, 1=user)",
                "examples": ["1", "100"],
                "constraints": "Non-null, >= 0"
            },
            # {
            #     "name": "user_status",
            #     "type": "INTEGER",
            #     "description": "Account status (1=active)",
            #     "examples": ["1", "0"],
            #     "constraints": "Non-null, 0 or 1"
            # },
            {
                "name": "email",
                "type": "TEXT",
                "description": "User's email address",
                "examples": ["", "user@example.com"],
                "constraints": "Can be empty"
            },
            {
                "name": "github_id",
                "type": "TEXT",
                "description": "User's GitHub ID for OAuth",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "oidc_id",
                "type": "TEXT",
                "description": "User's OpenID Connect ID",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "wechat_id",
                "type": "TEXT",
                "description": "User's WeChat ID",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "telegram_id",
                "type": "TEXT",
                "description": "User's Telegram ID",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "verification_code",
                "type": "TEXT",
                "description": "Verification code for account actions",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "access_token",
                "type": "TEXT",
                "description": "Access token for API access",
                "examples": ["null"],
                "constraints": "Can be null or empty"
            },
            {
                "name": "quota",
                "type": "INTEGER",
                "description": "Total quota allocated to this user",
                "examples": ["3942948534840", "644638609"],
                "constraints": "Non-null, >= 0",
                "usage": "Used for tracking resource allocation"
            },
            {
                "name": "used_quota",
                "type": "INTEGER",
                "description": "Amount of quota used by this user",
                "examples": ["1356897020248", "29939633"],
                "constraints": "Non-null, >= 0",
                "usage": "Used for tracking resource usage"
            },
            {
                "name": "request_count",
                "type": "INTEGER",
                "description": "Total number of API requests made by this user",
                "examples": ["157004654", "1430"],
                "constraints": "Non-null, >= 0",
                "aggregation": "Often summed to show total usage"
            },
            {
                "name": "user_group",
                "type": "TEXT",
                "description": "User group membership",
                "examples": ["default"],
                "constraints": "Non-null"
            },
            {
                "name": "aff_code",
                "type": "TEXT",
                "description": "User's affiliate code",
                "examples": ["CKDY", "FJ4B"],
                "constraints": "Can be empty"
            },
            {
                "name": "aff_count",
                "type": "INTEGER",
                "description": "Number of users referred through affiliate program",
                "examples": ["0"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "aff_quota",
                "type": "INTEGER",
                "description": "Quota earned through affiliate program",
                "examples": ["0"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "aff_history_quota",
                "type": "INTEGER",
                "description": "Historical total of quota earned through affiliate program",
                "examples": ["0"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "inviter_id",
                "type": "INTEGER",
                "description": "ID of the user who invited this user",
                "examples": ["0"],
                "constraints": "Non-null, >= 0"
            },
            {
                "name": "DeletedAt",
                "type": "TEXT",
                "description": "Timestamp when this user was deleted (null if not deleted)",
                "examples": ["null"],
                "constraints": "Can be null"
            },
            {
                "name": "linux_do_id",
                "type": "TEXT",
                "description": "Linux DO ID if applicable",
                "examples": [""],
                "constraints": "Can be empty"
            },
            {
                "name": "user_setting",
                "type": "TEXT",
                "description": "User-specific settings",
                "examples": [""],
                "constraints": "Can be empty or JSON"
            }
        ],
        "table_description": "Contains user account information including quota allocation and usage statistics",
        "common_queries": [
            "Users with highest quota usage",
            "Admin vs regular users",
            "Users by request count",
            "Active vs inactive users"
        ],
        "value_ranges": {
            "quota": "Typically ranges from millions to trillions",
            "used_quota": "Typically ranges from millions to trillions",
            "request_count": "Typically ranges from hundreds to millions"
        }
    }
}

def fetch_api_data(endpoint: str, params: Dict, session: str) -> Dict:
    """Fetch data from the API with the given endpoint and parameters, with retry mechanism"""
    # Ensure parameter order matches the curl command for consistency
    ordered_params = []
    
    # For /data/ endpoint, ensure this specific order that matches the curl command
    if endpoint == "/data/":
        param_order = ["username", "default_time", "start_timestamp", "end_timestamp"]
        for key in param_order:
            if key in params:
                ordered_params.append(f"{key}={params[key]}")
    else:
        # For other endpoints, just convert the dict to params
        ordered_params = [f"{k}={v}" for k, v in params.items()]
    
    query_string = "&".join(ordered_params)
    url = f"{BASE_URL}{endpoint}?{query_string}"
    
    # Set the Referer header dynamically based on the endpoint
    headers = HEADERS.copy()
    referer_page = "detail"  # Default referer
    if endpoint == "/token/":
        referer_page = "token"
    elif endpoint == "/log/":
        referer_page = "log"
    elif endpoint == "/channel/":
        referer_page = "channel"
    elif endpoint == "/pricing":
        referer_page = "pricing"
        
    headers['Referer'] = f'https://api.zhimiaonengzhi.com/{referer_page}'
    
    cookies = {'session': session}
    
    # Add retry mechanism for improved reliability
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Request attempt {attempt}/{max_retries} to {url}")
            print(f"Headers: {headers}")
            print(f"Cookies: {cookies}")
            
            # Note: verify=False to match the --insecure flag in curl
            response = requests.get(
                url, 
                headers=headers, 
                cookies=cookies, 
                verify=False,
                timeout=30  # Add timeout to prevent hanging requests
            )
            
            # Raise for non-2XX responses
            response.raise_for_status()
            
            response_data = response.json()
            print(f"API response status code: {response.status_code}")
            print(f"Response data type: {type(response_data)}")
            print(f"Response data preview: {str(response_data)[:500]}...")
            return response_data
            
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if hasattr(e, 'response') else None
            print(f"HTTP Error: {e} (Status code: {status_code})")
            
            # If we got a 502 error and have retries left, try again
            if status_code == 502 and attempt < max_retries:
                print(f"Got 502 error, retrying in {retry_delay} seconds...")
                import time
                time.sleep(retry_delay)
                continue
            
            # If it's the last attempt or not a 502 error, re-raise
            print(f"Failed after {attempt} attempts. Last error: {e}")
            raise
            
        except requests.RequestException as e:
            print(f"Error fetching data from {url}: {e}")
            
            # Retry on connection errors
            if attempt < max_retries:
                print(f"Retrying in {retry_delay} seconds...")
                import time
                time.sleep(retry_delay)
                continue
                
            print(f"Failed after {attempt} attempts. Last error: {e}")
            raise

def create_table(conn: sqlite3.Connection, table_name: str, schema: Dict) -> None:
    """Create a table based on the schema definition"""
    # Extract column definitions from schema
    columns = schema["columns"]
    col_defs = ", ".join([f"{col['name']} {col['type']}" for col in columns])
    
    # Create the table
    sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({col_defs})"
    print(f"Creating table with SQL: {sql}")
    conn.execute(sql)
    conn.commit()
    
    # Optional: Store metadata directly in SQLite for schema introspection
    # This could create a separate metadata table with all the descriptions,
    # examples, etc., that could be queried by tools or users

def insert_data(conn: sqlite3.Connection, table_name: str, data: List[Dict]) -> None:
    """Insert data into the table, handling column mappings and type conversions"""
    if not data:
        print(f"No data to insert for table {table_name}")
        return
        
    # Get column names from the schema
    schema = SCHEMA[table_name]
    columns = [col["name"] for col in schema["columns"]]
    column_types = {col["name"]: col["type"] for col in schema["columns"]}
    
    print(f"Processing data for table {table_name}")
    print(f"First item in data: {data[0] if isinstance(data, list) and len(data) > 0 else data}")
    print(f"Data type: {type(data)}")
    print(f"Expected columns: {columns}")
    
    # Process data before insertion
    processed_data = []
    try:
        for row in data:
            print(f"Processing row: {row}")
            print(f"Row type: {type(row)}")
            
            # Convert lists to JSON strings
            processed_row = {}
            for col in columns:
                try:
                    if isinstance(row, dict):
                        value = row.get(col)
                    else:
                        print(f"ERROR: Expected dict but got {type(row)}")
                        print(f"Row content: {row}")
                        raise TypeError(f"Expected dict but got {type(row)}")
                        
                    # Handle specific type conversions
                    if value is not None:
                        # Convert lists to JSON strings
                        if isinstance(value, list):
                            processed_row[col] = json.dumps(value, ensure_ascii=False)
                        # Convert booleans to integers for SQLite
                        elif isinstance(value, bool) and column_types[col] == "INTEGER":
                            processed_row[col] = 1 if value else 0
                        else:
                            processed_row[col] = value
                    else:
                        processed_row[col] = None
                except Exception as e:
                    print(f"Error processing column {col}: {e}")
                    raise
                    
            processed_data.append(processed_row)
    except Exception as e:
        print(f"Error in data processing loop: {e}")
        raise
    
    # Build and execute the INSERT statement
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    
    c = conn.cursor()
    for row in processed_data:
        values = [row.get(col) for col in columns]
        c.execute(insert_sql, values)
    
    conn.commit()
    print(f"Inserted {len(processed_data)} rows into table {table_name}")

def process_table(conn: sqlite3.Connection, table_name: str, session: str, 
                 start_timestamp: Optional[int] = None, 
                 end_timestamp: Optional[int] = None) -> None:
    """Process a single table: fetch data, create table, and insert data"""
    schema = SCHEMA[table_name]
    
    # Prepare parameters for API call
    params = schema["params"].copy()
    if start_timestamp and "start_timestamp" not in params:
        params["start_timestamp"] = start_timestamp
    if end_timestamp and "end_timestamp" not in params:
        params["end_timestamp"] = end_timestamp
        
    # Fetch data from API
    print(f"Fetching data for table {table_name}...")
    response_data = fetch_api_data(schema["endpoint"], params, session)
    
    # Extract relevant data from the response
    print(f"Extracting data using response_key: {schema['response_key']}")
    if schema["response_key"]:
        # Handle dot notation for nested paths (e.g., "data.items")
        if "." in schema["response_key"]:
            keys = schema["response_key"].split(".")
            data = response_data
            for key in keys:
                if isinstance(data, dict) and key in data:
                    data = data[key]
                    print(f"Extracted nested data using key '{key}', got type: {type(data)}")
                else:
                    print(f"WARNING: Could not find nested key '{key}' in data")
                    print(f"Data type: {type(data)}")
                    print(f"Data keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
                    raise KeyError(f"Could not find nested key '{key}' in data")
        elif isinstance(response_data, dict) and schema["response_key"] in response_data:
            data = response_data[schema["response_key"]]
            print(f"Extracted data using key '{schema['response_key']}', got type: {type(data)}")
        else:
            print(f"WARNING: Could not find key '{schema['response_key']}' in response or response is not a dict")
            print(f"Response type: {type(response_data)}")
            print(f"Response keys: {response_data.keys() if isinstance(response_data, dict) else 'N/A'}")
            raise KeyError(f"Could not find key '{schema['response_key']}' in response")
    else:
        data = response_data
        print(f"Using entire response as data, type: {type(data)}")
    
    # Create table and insert data
    create_table(conn, table_name, schema)
    insert_data(conn, table_name, data)

def export_schema_for_nl2sql():
    """Export the schema in a format compatible with nl_to_sql.py"""
    nl2sql_schema = {}
    
    for table_name, schema in SCHEMA.items():
        table_info = {
            "table_description": schema.get("table_description", f"Table containing {table_name} data"),
            "columns": [],
            "time_series_nature": schema.get("time_series_nature", ""),
            "common_queries": schema.get("common_queries", []),
            "value_ranges": schema.get("value_ranges", {})
        }
        
        for col in schema["columns"]:
            column_info = {
                "name": col["name"],
                "type": col["type"],
                "description": col["description"],
                "examples": col["examples"],
                "constraints": col["constraints"]
            }
            
            # Add optional fields if present
            for optional in ["usage", "aggregation"]:
                if optional in col:
                    column_info[optional] = col[optional]
                    
            table_info["columns"].append(column_info)
            
        nl2sql_schema[table_name] = table_info
    
    # Option 1: Return the schema for use in nl_to_sql.py
    return nl2sql_schema
    
    # Option 2: Write to a file that nl_to_sql.py can import
    # with open('schema_for_nl2sql.json', 'w') as f:
    #     json.dump(nl2sql_schema, f, indent=2)

def get_table_stats(db_file=DB_FILE):
    """Get statistics about all tables in the database"""
    if not os.path.exists(db_file):
        print(f"Database {db_file} does not exist yet.")
        return {}
    
    stats = {}
    conn = sqlite3.connect(db_file)
    
    # Get list of all tables
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    
    for table in tables:
        try:
            # Get record count
            c.execute(f"SELECT COUNT(*) FROM {table}")
            count = c.fetchone()[0]
            
            # Get min/max timestamps for time-series tables
            time_col = None
            if table in SCHEMA and any(col["name"] == "created_at" for col in SCHEMA[table]["columns"]):
                time_col = "created_at"
            
            if time_col:
                c.execute(f"SELECT MIN({time_col}), MAX({time_col}) FROM {table}")
                min_time, max_time = c.fetchone()
                
                # Convert to human readable format
                from datetime import datetime
                min_date = datetime.fromtimestamp(min_time).strftime('%Y-%m-%d %H:%M:%S') if min_time else "N/A"
                max_date = datetime.fromtimestamp(max_time).strftime('%Y-%m-%d %H:%M:%S') if max_time else "N/A"
                
                stats[table] = {
                    "count": count,
                    "date_range": f"{min_date} to {max_date}" if min_time and max_time else "N/A"
                }
            else:
                stats[table] = {"count": count}
            
            # Add additional stats for specific tables
            if table == "model_stats":
                c.execute("SELECT COUNT(DISTINCT model_name) FROM model_stats")
                model_count = c.fetchone()[0]
                stats[table]["unique_models"] = model_count
            
            elif table == "log":
                c.execute("SELECT COUNT(DISTINCT username) FROM log")
                user_count = c.fetchone()[0]
                stats[table]["unique_users"] = user_count
                
                c.execute("SELECT COUNT(DISTINCT model_name) FROM log")
                model_count = c.fetchone()[0]
                stats[table]["unique_models"] = model_count
            
        except sqlite3.Error as e:
            stats[table] = {"error": str(e)}
    
    conn.close()
    return stats

def print_table_stats(stats):
    """Print table statistics in a formatted way"""
    if not stats:
        print("\nNo database statistics available yet.")
        return
        
    print("\n=== DATABASE STATISTICS ===")
    for table, table_stats in stats.items():
        print(f"\n{table}:")
        print("-" * len(table))
        
        for key, value in table_stats.items():
            print(f"  {key}: {value}")
    
    # Print total records
    total_records = sum(stats[table].get('count', 0) for table in stats)
    print("\nTotal records across all tables:", total_records)

def main():
    parser = argparse.ArgumentParser(description='Import data from APIs into SQLite database')
    parser.add_argument('--lastdays', type=int, help='Import data for the last N days')
    parser.add_argument('--session', type=str, help='Session cookie value')
    parser.add_argument('--tables', type=str, default='all', 
                       help='Comma-separated list of tables to import, or "all"')
    parser.add_argument('--force', action='store_true', 
                       help='Force import even if database exists')
                       
    args = parser.parse_args()
    
    # Session is required for data import
    if not args.session:
        print("Error: Session cookie value is required for data import. Use --session.")
        return
    
    # Check if database exists
    if os.path.exists(DB_FILE) and not args.force:
        print(f"Database {DB_FILE} already exists. Use --force to reimport.")
        
        # Display current database statistics even if we're not importing
        print("\nCurrent database statistics:")
        stats = get_table_stats(DB_FILE)
        print_table_stats(stats)
        return
        
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(DB_FILE)
    
    # Determine which tables to process
    if args.tables.lower() == 'all':
        tables = list(SCHEMA.keys())
    else:
        tables = [t.strip() for t in args.tables.split(',')]
        # Validate table names
        for table in tables:
            if table not in SCHEMA:
                print(f"Warning: Table '{table}' not found in schema")

    # Calculate start and end timestamps based on --lastdays
    if args.lastdays:
        end = int(datetime.now().timestamp())
        start = end - (args.lastdays * 86400)  # 86400 seconds in a day
    else:
        print("Error: --lastdays is required. Please specify the number of days.")
        return
        
    # Track the number of records imported for each table
    import_counts = {}
    
    try:
        # Process each table
        for table in tables:
            if table in SCHEMA:
                try:
                    # Count records before import
                    count_before = 0
                    try:
                        c = conn.cursor()
                        c.execute(f"SELECT COUNT(*) FROM {table}")
                        count_before = c.fetchone()[0]
                    except sqlite3.OperationalError:
                        # Table might not exist yet
                        pass
                    
                    process_table(conn, table, args.session, start, end)
                    
                    # Count records after import
                    c = conn.cursor()
                    c.execute(f"SELECT COUNT(*) FROM {table}")
                    count_after = c.fetchone()[0]
                    
                    # Calculate how many were added
                    records_added = count_after - count_before
                    import_counts[table] = records_added
                    
                    print(f"Successfully processed table {table}")
                except Exception as e:
                    print(f"Error processing table {table}: {e}")
                    import_counts[table] = "Error"
            else:
                print(f"Skipping unknown table: {table}")
    finally:
        # Close connection
        conn.close()
        print(f"All data imported into {DB_FILE}")
        
        # Print summary of imported records
        print("\n=== IMPORT SUMMARY ===")
        print(f"{'Table':<15} {'Records Imported':<20}")
        print("-" * 35)
        for table, count in import_counts.items():
            print(f"{table:<15} {count:<20}")
        print("=" * 35)
        total_success = sum([count for count in import_counts.values() if isinstance(count, int)])
        print(f"Total records successfully imported: {total_success}")
        
        # Print detailed statistics about all tables - always do this regardless of errors
        print("\nDetailed database statistics:")
        stats = get_table_stats(DB_FILE)
        print_table_stats(stats)
        
        # Example of exporting schema for nl_to_sql.py
        # schema_for_nl2sql = export_schema_for_nl2sql()
        # print("Generated schema for nl_to_sql.py")

if __name__ == '__main__':
    main() 