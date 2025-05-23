#!/usr/bin/env python3
import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
import pymysql
from pymysql import Error
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Populate channel data from quota data')
    parser.add_argument('--db_name', 
                       required=True,  # Make it required instead of having a default
                       help='Database profile name from databases.yaml')
    return parser.parse_args()

def load_config(db_name):
    """Load database configuration from config/databases.yaml"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'databases.yaml')
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        if db_name not in config:
            logger.error(f"Database profile '{db_name}' not found in config")
            logger.info(f"Available profiles: {', '.join(config.keys())}")
            sys.exit(1)
            
        if config[db_name]['type'] != 'mysql':
            logger.error(f"Database profile '{db_name}' is not a MySQL database")
            sys.exit(1)
            
        return config[db_name]['connection']
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        sys.exit(1)

def get_db_connection(config):
    """Create database connection using configuration"""
    try:
        connection = pymysql.connect(
            host=config['host'],
            user=config['user'],
            password=config['password'],
            database=config['database'],
            port=config['port'],
            charset=config['charset'],
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except Error as e:
        logger.error(f"Error connecting to database: {e}")
        sys.exit(1)

def check_existing_data(connection, timestamp):
    """Check if data already exists for the given timestamp"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM channel_data 
                WHERE created_at = %s
            """, (timestamp,))
            result = cursor.fetchone()
            return result['count'] > 0
    except Error as e:
        logger.error(f"Error checking existing data: {e}")
        return False

def get_all_timestamps(connection):
    """Get all timestamps from quota_data table"""
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT DISTINCT created_at
                FROM quota_data
                ORDER BY created_at DESC
            """
            # logger.info("Generated SQL query for timestamps:")
            # logger.info(f"Query: {query}")
            
            cursor.execute(query)
            # Keep timestamps as integers
            return [row['created_at'] for row in cursor.fetchall()]
    except Error as e:
        logger.error(f"Error getting timestamps: {e}")
        return []

def get_existing_timestamps(connection):
    """Get all timestamps that already have data in channel_data"""
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT DISTINCT created_at
                FROM channel_data
                ORDER BY created_at
            """
            logger.info("Generated SQL query for existing timestamps:")
            logger.info(f"Query: {query}")
            
            cursor.execute(query)
            # Keep timestamps as integers
            return {row['created_at'] for row in cursor.fetchall()}
    except Error as e:
        logger.error(f"Error getting existing timestamps: {e}")
        return set()

def get_channel_name_map(connection):
    """Get a dictionary mapping channel_id to channel_name from channels table"""
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT id, name
                FROM channels
            """
            cursor.execute(query)
            return {row['id']: row['name'] for row in cursor.fetchall()}
    except Error as e:
        logger.error(f"Error getting channel names: {e}")
        return {}

def get_channel_summary(connection, start_time, end_time):
    """Get channel summary data for the given time range"""
    try:
        with connection.cursor() as cursor:
            query = """
                SELECT 
                    channel_id,
                    SUM(completion_tokens + prompt_tokens) as token_used,
                    COUNT(*) as count,
                    SUM(quota) as quota
                FROM logs
                WHERE created_at >= %s AND created_at < %s
                GROUP BY channel_id
            """
            params = (start_time, end_time)
            
            # Log the SQL query with parameters
            logger.info("Generated SQL query:")
            logger.info(f"Query: {query}")
            logger.info(f"Parameters: start_time={start_time}, end_time={end_time}")
            
            # Execute the main query
            cursor.execute(query, params)
            return cursor.fetchall()
    except Error as e:
        logger.error(f"Error getting channel summary: {e}")
        return []

def insert_channel_data(connection, data, timestamp, channel_name_map):
    """Insert channel data into the channel_data table"""
    try:
        with connection.cursor() as cursor:
            insert_query = """
                INSERT INTO channel_data 
                (channel_id, channel_name, created_at, token_used, count, quota)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            # Ensure timestamp is an integer
            if isinstance(timestamp, datetime):
                timestamp = int(timestamp.timestamp())
            
            values = [
                (row['channel_id'], 
                 channel_name_map.get(row['channel_id'], 'Unknown'),  # Use channel_name_map to get name
                 timestamp, 
                 row['token_used'], 
                 row['count'], 
                 row['quota'])
                for row in data
            ]
            
            # Log the insert query and first few values
            logger.info("Generated INSERT query:")
            logger.info(f"Query: {insert_query}")
            if values:
                logger.info(f"First value set: {values[0]}")
                logger.info(f"Total records to insert: {len(values)}")
            
            cursor.executemany(insert_query, values)
        connection.commit()
        return True
    except Error as e:
        logger.error(f"Error inserting channel data: {e}")
        connection.rollback()
        return False

def main():
    # Parse command line arguments
    args = parse_args()
    logger.info(f"Using database profile: {args.db_name}")
    
    # Load configuration
    config = load_config(args.db_name)
    logger.info(f"Connecting to database: {config['database']}")
    
    # Get database connection
    connection = get_db_connection(config)
    
    try:
        # Get channel name mapping
        channel_name_map = get_channel_name_map(connection)
        logger.info(f"Loaded {len(channel_name_map)} channel names")
        
        # Get all timestamps from quota_data
        all_timestamps = get_all_timestamps(connection)
        if not all_timestamps:
            logger.error("No data found in quota_data table")
            return
        
        logger.info(f"Found {len(all_timestamps)} timestamps in quota_data")
        
        # Get existing timestamps in channel_data
        existing_timestamps = get_existing_timestamps(connection)
        logger.info(f"Found {len(existing_timestamps)} existing timestamps in channel_data")
        
        # Find timestamps that need processing
        timestamps_to_process = [ts for ts in all_timestamps if ts not in existing_timestamps]
        logger.info(f"Found {len(timestamps_to_process)} timestamps to process")
        
        # Process each timestamp
        for timestamp in timestamps_to_process:
            start_time = timestamp
            end_time = timestamp + 3600  # Add 3600 seconds (1 hour) to get end time

            # Check if data already exists for this timestamp
            if check_existing_data(connection, timestamp):
                logger.info(f"channel_data already exists for timestamp {timestamp}, skipping.")
                break

            logger.info(f"Processing time range: {start_time} to {end_time}")
            
            # Get channel summary data
            channel_summary = get_channel_summary(connection, start_time, end_time)
            if not channel_summary:
                logger.info(f"No channel data found for timestamp {timestamp}")
                continue
            
            # Insert the data
            if insert_channel_data(connection, channel_summary, timestamp, channel_name_map):
                logger.info(f"Successfully inserted {len(channel_summary)} channel records for timestamp {timestamp}")
            else:
                logger.error(f"Failed to insert channel data for timestamp {timestamp}")
    
    finally:
        connection.close()

if __name__ == "__main__":
    main()
