# 🏛️ AI Floor Plan Generator — Tamil Nadu

**An Explainable AI Framework for Climate-Responsive Building Design and
Sustainable Material Selection in Tamil Nadu**

Inspired by Laurie Baker Principles

---

## 🚀 Quick Start (5 minutes)

```bash
# 1. Create a folder and place all 3 files inside:
#    app.py, engine.py, renderer.py, requirements.txt

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`

---

## 📁 File Structure

```
floorplan_tn/
├── app.py          ← Streamlit UI (run this)
├── engine.py       ← Floor plan generation logic
├── renderer.py     ← Matplotlib drawing engine
├── requirements.txt
└── README.md
```

---

## 🔑 Key Features

### Tamil Nadu Climate Zones
- Coastal (Chennai, Pondicherry) — Hot humid
- Inland Semi-Arid (Madurai, Salem) — Hot dry
- Hilly (Ooty, Kodaikanal) — Temperate cool
- Western Ghats (Coimbatore foothills) — Hot humid wet

### Laurie Baker Principles (Computable)
| Principle | Computable Rule |
|-----------|----------------|
| Rat-Trap Bond | wall_thickness ≥ 200mm + cavity |
| Jali Screens | West/SW facing windows → add jali |
| Courtyard | plot > 100m² → add min 9m² courtyard |
| Deep Overhangs | overhang = window_height × tan(latitude) |
| Cross-ventilation | inlet facing prevailing wind + outlet opposite |
| Local Materials | country brick, Mangalore tile, lime mortar |

### AI Explainability (XAI)
Every design decision is explained:
- Why rooms are placed where they are
- Why windows face specific directions
- How climate data influenced decisions
- Which Baker principles are applied and why

### Scoring System (6 metrics)
1. Space Efficiency
2. Aspect Ratio Quality
3. Natural Ventilation
4. Climate Responsiveness
5. Baker Compliance
6. NBC (National Building Code) Compliance

---

## 🏠 Supported BHK Types
- 1BHK
- 2BHK
- 2BHK + Pooja Room
- 3BHK
- 3BHK + Courtyard (traditional Tamil Nadu layout)

---

## 🧮 Algorithm

1. **Room Sizing** — Scale room areas to fit usable plot area (70% of plot)
2. **Squarified Treemap** — Place rooms minimising worst aspect ratio (same algorithm from Lan's presentation)
3. **Climate Analysis** — Determine prevailing wind, solar radiation, challenges
4. **Window Assignment** — Inlet from prevailing wind, outlet on opposite face
5. **Scoring** — Evaluate 6 objectives
6. **Explanation Generation** — Explain every decision in plain language

---

## 📝 For Mentor Review

**Project Title Justification:**
> "An Explainable AI Framework for Climate-Responsive Building Design"

- **Explainable AI**: Every decision traced and explained (see XAI tab)
- **Climate-Responsive**: 4 TN climate zones with different design responses
- **Building Design**: Complete floor plan with rooms, walls, windows, doors
- **Tamil Nadu**: Local climate data, local materials, local context
- **Laurie Baker**: Computable design rules from his sustainable architecture

**Novel Contribution:**
Making Laurie Baker's intuitive principles *quantifiable and explainable* through AI — converting architectural wisdom into computable constraints.
