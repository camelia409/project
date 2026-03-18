from engine import generate_floor_plan
from renderer import render_floorplan
for bhk in ["1BHK", "2BHK", "3BHK"]:
    fp = generate_floor_plan(12, 15, bhk, 'Coastal (Chennai, Pondicherry, Nagapattinam)', facing='North')
    fig = render_floorplan(fp)
    fig.savefig(f'test_{bhk}.png', dpi=150, bbox_inches='tight')
