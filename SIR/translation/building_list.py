import requests
import pandas as pd
import time

def extract_e_ward_buildings():
    # The official query endpoint for BMC Building ID
    base_url = "https://mybmcid.mcgm.gov.in/server/rest/services/MyBMC_Building_ID/FeatureServer/0/query"
    
    all_features = []
    offset = 0
    batch_size = 1000 # Standard ArcGIS limit
    
    while True:
        params = {
            'where': "WARD_NAME = 'E'", # Note: Case sensitivity matters (might be 'E' or 'E WARD')
            'outFields': '*',           # All columns: SAC No, Building Name, Address, etc.
            'f': 'json',                # Format
            'resultOffset': offset,     # Start point for this batch
            'resultRecordCount': batch_size,
            'returnGeometry': 'false'   # Faster since you just want the list
        }
        
        print(f"Fetching records starting from {offset}...")
        
        try:
            response = requests.get(base_url, params=params, timeout=30)
            data = response.json()
            
            # Extract features from the current batch
            features = data.get('features', [])
            if not features:
                break # No more data to fetch
                
            # Flatten the nested 'attributes' key
            batch_list = [f['attributes'] for f in features]
            all_features.extend(batch_list)
            
            # Check if we should continue
            if 'exceededTransferLimit' in data or len(features) == batch_size:
                offset += batch_size
                time.sleep(1) # Polite delay
            else:
                break
                
        except Exception as e:
            print(f"Error occurred: {e}")
            break

    # Save to CSV
    if all_features:
        df = pd.DataFrame(all_features)
        df.to_csv("EWard_Buildings_List.csv", index=False)
        print(f"Successfully saved {len(df)} buildings to EWard_Buildings_List.csv")
    else:
        print("No data found. Check if WARD_NAME field is correct.")

if __name__ == "__main__":
    extract_e_ward_buildings()