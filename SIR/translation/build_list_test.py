import requests
import pandas as pd
import json

def get_e_ward_data():
    # This is the direct query URL for the Building Layer
    url = "https://mybmcid.mcgm.gov.in/server/rest/services/MyBMC_Building_ID/FeatureServer/0/query"
    
    # Essential headers to avoid '403 Forbidden' or empty responses
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0',
        'Referer': 'https://mybmcid.mcgm.gov.in/portal/apps/experiencebuilder/experience/?id=...',
        'Origin': 'https://mybmcid.mcgm.gov.in'
    }

    # Parameters to test the field values
    # We use '1=1' first to see what the 'WARD' values actually look like
    params = {
        'f': 'json',
        'where': "WARD_NAME LIKE '%E%' OR WARD LIKE '%E%'", # Flexible search
        'outFields': 'OBJECTID,WARD_NAME,BUILDING_NAME,ADDRESS,SAC_NO',
        'returnGeometry': 'false',
        'resultRecordCount': 500
    }

    print("Connecting to BMC GIS Server...")
    
    try:
        response = requests.get(url, params=params, headers=headers, verify=True)
        
        if response.status_code != 200:
            print(f"Server returned error {response.status_code}")
            return

        data = response.json()
        
        if 'features' in data and len(data['features']) > 0:
            # Convert attributes to a list of dicts
            records = [f['attributes'] for f in data['features']]
            df = pd.DataFrame(records)
            
            # Save to CSV
            df.to_csv("E_Ward_Buildings.csv", index=False)
            print(f"Success! Found {len(df)} buildings. Saved to E_Ward_Buildings.csv")
            print("\nSample Data:")
            print(df.head())
        else:
            print("No features returned. The server might be using a different field name.")
            print("Response hint:", data.get('error', 'No error message provided'))
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    get_e_ward_data()