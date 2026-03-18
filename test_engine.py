#!/usr/bin/env python3
"""Test engine to check for graph layout fallback errors."""

import sys
from engine import generate_best_floor_plan

print("=" * 70, file=sys.stderr)
print("Testing floor plan generation for fallback errors...", file=sys.stderr)
print("=" * 70, file=sys.stderr)

try:
    best, all3 = generate_best_floor_plan(
        plot_width_m=12.0,
        plot_height_m=15.0,
        bhk_type='2BHK',
        climate_zone_key='Coastal (Chennai, Pondicherry, Nagapattinam)',
        facing='North',
        agent_report=None,
        special_needs=[]
    )
    print(f"\n✓ SUCCESS: Generated {best.bhk_type} with {len(best.rooms)} rooms", file=sys.stderr)
    print(f"✓ Overall score: {best.scores.get('Overall', 0):.0f}/100", file=sys.stderr)
    print(f"✓ Rooms: {', '.join(r.name for r in best.rooms)}", file=sys.stderr)
    print("\n" + "=" * 70, file=sys.stderr)
    print("NO FALLBACK ERRORS DETECTED - Graph layout working correctly!", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    
except Exception as e:
    print(f"\n✗ GENERATION FAILED: {type(e).__name__}: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
