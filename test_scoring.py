#!/usr/bin/env python3
"""Test the new hazard scoring system with dynamic thresholds"""

import sys
sys.path.insert(0, 'scripts')

try:
    from hazard_score_v2 import hazard_score_v2
    using_v2 = True
except ImportError:
    print("⚠️  hazard_score_v2 not available yet, using old system")
    from model import hazard_score
    using_v2 = False

if not using_v2:
    # Test with old system
    print("\n" + "="*80)
    print("Testing OLD hazard scoring system")
    print("="*80)
    test_data = {"temp": 35.5, "prcp": 45.0, "wind": 12.0, "pressure": 1005.0}
    event = hazard_score(test_data, explain=False)
    print(f"Old system result: event={event}")
    print("\nWaiting for PR to complete to test new system...")
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
            print(f"   Multipliers: {details.get('client_multipliers', {})}")
            
            if details.get('triggered_thresholds'):
                print(f"   Triggered thresholds:")
                for var, info in details['triggered_thresholds'].items():
                    print(f"      - {var}: {info['value']:.1f} > {info['adjusted_threshold']:.1f} " +
                          f"({info.get('percentile', 'N/A')})")
        
        except Exception as e:
            print(f"\n❌ Client: {client_id} - ERROR: {e}")
            import traceback
            traceback.print_exc()

print("\n" + "=" * 80)
print("✅ Test complete!")
print("=" * 80)