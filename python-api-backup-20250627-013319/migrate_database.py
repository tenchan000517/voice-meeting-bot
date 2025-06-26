"""
Database migration script to add missing columns
"""
import sqlite3
import os
from datetime import datetime

def migrate_database():
    """Add missing columns to processing_status table"""
    db_path = "meetings.db"
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(processing_status)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add missing columns
        if 'total_chunks' not in columns:
            print("Adding total_chunks column...")
            cursor.execute("ALTER TABLE processing_status ADD COLUMN total_chunks INTEGER DEFAULT 0")
            print("✓ Added total_chunks column")
        else:
            print("total_chunks column already exists")
            
        if 'completed_chunks' not in columns:
            print("Adding completed_chunks column...")
            cursor.execute("ALTER TABLE processing_status ADD COLUMN completed_chunks INTEGER DEFAULT 0")
            print("✓ Added completed_chunks column")
        else:
            print("completed_chunks column already exists")
        
        conn.commit()
        print("\nDatabase migration completed successfully!")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()