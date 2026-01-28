#!/usr/bin/env python3
"""Test the new hazard scoring system"""

import sys
import os

# Load environment variables FIRST
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, 'scripts')

try:
    from hazard_score_v2 import hazard_score_v2
    print("✅ Using hazard_score_v2 (new system)")
except ImportError:
    print("⚠️  hazard_score_v2 not found - PR still building")
    print("   The new files will be available once the PR completes.")
    print("   Current endpoint uses old hardcoded thresholds.")
    sys.exit(0)

# Test scenarios
test_cases = [
    {
        "name": "Normal day",
        "data": {"temp": 28.5, "prcp": 0, "wind": 5.0, "pressure": 1012.0},
        "month": 8
    },
    {
        "name": "Heavy rain (wet season)",
        "data": {"temp": 27.0, "prcp": 55.0, "wind": 12.0, "pressure": 1005.0},
        "month": 8
    },
    {
        "name": "Extreme heat (dry season)",
        "data": {"temp": 38.5, "prcp": 0, "wind": 3.0, "pressure": 1011.0},
        "month": 4
    },
    {
        "name": "Storm forming",
        "data": {"temp": 26.0, "prcp": 15.0, "wind": 22.0, "pressure": 998.0},
        "month": 10
    }
]

clients = ["default", "zone_a_mountain", "zone_b_coastal"]

print("=" * 80)
print("HAZARD SCORING TEST - DYNAMIC THRESHOLDS")
print("=" * 80)
print(f"Database: {os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}")
print("=" * 80)

for test in test_cases:
    print(f"\n{'='*80}")
    print(f"TEST: {test['name']} (Month: {test['month']})")
    print(f"Weather: Temp={test['data']['temp']}°C, Rain={test['data']['prcp']}mm, "
          f"Wind={test['data']['wind']}m/s, Pressure={test['data']['pressure']}hPa")
    print(f"{'='*80}")
    
    for client_id in clients:
        try:
            event, score, hazards, details = hazard_score_v2(
                row=test['data'],
                thresholds_path="thresholds/sanpedro_monthly_v1.json",
                client_id=client_id,
                month=test['month'],
                explain=True
            )
            
            print(f"\n📍 Client: {client_id}")
            print(f"   Event: {'🚨 HAZARD' if event else '✅ SAFE'} (score: {score:.2f})")
            if hazards:
                print(f"   Hazards: {', '.join(hazards)}")
            
            multipliers = details.get('client_multipliers', {})
            print(f"   Multipliers: rain={multipliers.get('rain', 1.0):.2f}, "
                  f"wind={multipliers.get('wind', 1.0):.2f}, "
                  f"heat={multipliers.get('heat', 1.0):.2f}")
            
            if details.get('triggered_thresholds'):
                print(f"   Triggered:")
                for var, info in details['triggered_thresholds'].items():
                    print(f"      - {var}: {info['value']:.1f} > {info['adjusted_threshold']:.1f}")
        
        except Exception as e:
            print(f"\n❌ Client: {client_id} - ERROR: {e}")

print("\n" + "=" * 80)
print("✅ Test complete!")