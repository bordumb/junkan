import os
import boto3

def connect():
    # CRITICAL DEPENDENCY: If this env var changes, the app crashes.
    host = os.getenv("PAYMENT_DB_HOST")
    print(f"Connecting to {host}...")
