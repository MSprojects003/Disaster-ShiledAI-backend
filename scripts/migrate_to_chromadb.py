"""
Migrate from FAISS to ChromaDB
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.rag_service_chroma import chroma_rag

def migrate_to_chromadb():
    """Migrate existing data to ChromaDB"""
    
    print("="*60)
    print("🔄 Migrating to ChromaDB")
    print("="*60)
    
    # Step 1: Check ChromaDB status
    status = chroma_rag.get_status()
    print(f"\n📊 ChromaDB Status:")
    print(f"   Enabled: {status['enabled']}")
    print(f"   Gemini: {status['gemini_enabled']}")
    print(f"   Knowledge Count: {status['knowledge_collection']['count']}")
    print(f"   Shelter Count: {status['shelter_collection']['count']}")
    
    # Step 2: Migrate knowledge from JSON
    print("\n📚 Migrating knowledge...")
    knowledge_path = 'data/rag/knowledge/default_knowledge.json'
    if os.path.exists(knowledge_path):
        with open(knowledge_path, 'r') as f:
            knowledge = json.load(f)
        
        for item in knowledge:
            content = item.get('content', '')
            category = item.get('category', 'general')
            chroma_rag.add_knowledge(content, category)
            print(f"   ✅ Added: {content[:50]}...")
    else:
        print("   ⚠️ No knowledge file found")
    
    # Step 3: Migrate shelters from CSV
    print("\n🏠 Migrating shelters...")
    shelter_path = 'data/evacuation/processed/shelters.csv'
    if os.path.exists(shelter_path):
        df = pd.read_csv(shelter_path)
        shelters = df.to_dict('records')
        
        for shelter in shelters:
            chroma_rag.add_shelter(shelter)
            print(f"   ✅ Added: {shelter.get('name', 'Unknown')}")
    else:
        print("   ⚠️ No shelter file found")
    
    # Step 4: Final status
    print("\n📊 Final ChromaDB Status:")
    status = chroma_rag.get_status()
    print(f"   Knowledge: {status['knowledge_collection']['count']} documents")
    print(f"   Shelters: {status['shelter_collection']['count']} shelters")
    print(f"   Data Path: {status['data_path']}")
    
    print("\n✅ Migration complete!")
    print("\n📁 ChromaDB data stored at: data/chromadb/")

if __name__ == "__main__":
    migrate_to_chromadb()