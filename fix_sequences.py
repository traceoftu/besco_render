#!/usr/bin/env python3
"""
PostgreSQL 시퀀스 재설정 스크립트
"""

import requests
import sys

def fix_sequences():
    """시퀀스 재설정 API 호출"""
    url = "https://besco-render.onrender.com/fix-sequences/"
    headers = {"X-API-Key": "your_secret_api_key_here"}
    
    try:
        print("Calling fix-sequences API...")
        response = requests.post(url, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Sequences fixed successfully!")
            return True
        else:
            print("❌ Failed to fix sequences")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = fix_sequences()
    sys.exit(0 if success else 1)
