# -*- coding: utf-8 -*-
"""Test doors: verify every room gets a door_side assigned."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from engine import generate_best_floor_plan

plan, _ = generate_best_floor_plan(12, 15, "3BHK",
    "Coastal (Chennai, Pondicherry, Nagapattinam)", "North")

print(f"{'Name':14s} {'type':10s} {'door':5s} {'adj':s}")
print("-" * 60)
for r in plan.rooms:
    adj = ', '.join(r.adjacent_to[:3]) if r.adjacent_to else '-'
    print(f"  {r.name:12s} {r.room_type:10s} {r.door_side:5s} {adj}")

# Test rendering
from renderer import render_floorplan
import matplotlib
matplotlib.use("Agg")
fig = render_floorplan(plan)
fig.savefig("test_doors.png", dpi=100)
print("\nSaved test_doors.png")
