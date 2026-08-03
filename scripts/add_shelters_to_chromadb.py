# add_shelters_to_chromadb.py
import os
import sys
import pandas as pd
sys.path.append('.')

from app.services.rag_service_chroma import chroma_rag

def add_shelters_to_chromadb():
    """Add shelter data from CSV to ChromaDB"""
    
    csv_path = 'data/evacuation/processed/shelters.csv'
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return False
    
    # Read CSV
    df = pd.read_csv(csv_path)
    shelters = df.to_dict('records')
    
    print(f"📊 Found {len(shelters)} shelters in CSV")
    
    # Add each shelter to ChromaDB
    added_count = 0
    for shelter in shelters:
        # Prepare the dictionary for ChromaDB
        shelter_data = {
            'shelter_id': shelter.get('shelter_id', ''),
            'name': shelter.get('name', 'Unknown Shelter'),
            'type': shelter.get('type', 'Unknown'),
            'district': shelter.get('district', 'Unknown'),
            'lat': shelter.get('lat', 0),
            'lon': shelter.get('lon', 0),
            'capacity': shelter.get('capacity', 200),
            'available': shelter.get('available', 180),
            'source': shelter.get('source', 'CSV')
        }
        
        try:
            # Call add_shelter with the dictionary
            result = chroma_rag.add_shelter(shelter_data)
            if result:
                added_count += 1
                print(f"✅ Added: {shelter.get('name', 'Unknown')}")
            else:
                print(f"❌ Failed to add: {shelter.get('name', 'Unknown')}")
        except Exception as e:
            print(f"❌ Error adding {shelter.get('name', 'Unknown')}: {e}")
    
    print(f"\n✅ Total added: {added_count} shelters to ChromaDB")
    return True

if __name__ == "__main__":
    print("🗄️ Adding shelters to ChromaDB...")
    print("="*40)
    add_shelters_to_chromadb()