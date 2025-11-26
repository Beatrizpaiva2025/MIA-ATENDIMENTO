"""
Setup Leads - Populate MongoDB with sample data
Run once to initialize the leads and marketing_stats collections
"""

import os
import json
from pymongo import MongoClient
from datetime import datetime

print("🔄 Starting Leads Setup...")

# MongoDB connection
mongodb_uri = os.getenv('MONGODB_URI')
if not mongodb_uri:
    print("❌ ERROR: MONGODB_URI not found in environment variables")
    exit(1)

try:
    client = MongoClient(mongodb_uri)
    db = client.get_default_database()
    print(f"✅ Connected to MongoDB: {db.name}")
except Exception as e:
    print(f"❌ Failed to connect to MongoDB: {e}")
    exit(1)

# Load sample data
print("📂 Loading sample data...")
try:
    with open('sample_data.json', 'r') as f:
        data = json.load(f)
    print(f"✅ Sample data loaded: {len(data['leads'])} leads, {len(data['marketing_stats'])} stats")
except Exception as e:
    print(f"❌ Failed to load sample_data.json: {e}")
    exit(1)

# Clear existing data (optional - comment out if you want to keep existing)
print("🗑️  Clearing existing data...")
db['leads'].delete_many({})
db['marketing_stats'].delete_many({})
print("✅ Existing data cleared")

# Insert leads
print(f"📝 Inserting {len(data['leads'])} leads...")
try:
    if data['leads']:
        db['leads'].insert_many(data['leads'])
    print("✅ Leads inserted successfully")
except Exception as e:
    print(f"❌ Failed to insert leads: {e}")
    exit(1)

# Insert marketing stats
print(f"📊 Inserting {len(data['marketing_stats'])} marketing stats...")
try:
    if data['marketing_stats']:
        db['marketing_stats'].insert_many(data['marketing_stats'])
    print("✅ Marketing stats inserted successfully")
except Exception as e:
    print(f"❌ Failed to insert marketing stats: {e}")
    exit(1)

# Create indexes
print("🔧 Creating indexes...")
try:
    db['leads'].create_index('created_at')
    db['leads'].create_index('status')
    db['leads'].create_index('origin')
    db['marketing_stats'].create_index('date')
    print("✅ Indexes created successfully")
except Exception as e:
    print(f"⚠️  Warning: Failed to create some indexes: {e}")

# Verify
leads_count = db['leads'].count_documents({})
stats_count = db['marketing_stats'].count_documents({})

print("\n" + "="*60)
print("🎉 SETUP COMPLETED SUCCESSFULLY!")
print("="*60)
print(f"✅ Leads inserted: {leads_count}")
print(f"✅ Marketing stats inserted: {stats_count}")
print(f"📅 Date range: {data['metadata']['date_range']['start'][:10]} to {data['metadata']['date_range']['end'][:10]}")
print("\n🚀 Ready to use! Access your dashboard now:")
print("   https://mia-atendimento-1.onrender.com/admin/leads")
print("="*60)
