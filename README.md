# 🏛️ AI Floor Plan Generator — Tamil Nadu

**An Explainable AI Framework for Climate-Responsive Building Design and Sustainable Architecture in Tamil Nadu**

Inspired by Laurie Baker Principles & NBC Standards.

---

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/camelia409/project.git
cd project

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
streamlit run app.py
```

The app will be available at `http://localhost:8501`

---

## 📁 Project Structure

```
Final/
├── app.py                  # Streamlit UI & Application Entry
├── engine.py               # Core layout generation engine
├── renderer.py             # Advanced Matplotlib rendering engine
├── agents/                 # Specialized AI Agents
│   ├── baker_agent.py      # Laurie Baker design principles
│   ├── climate_agent.py    # Climate zone & orientation logic
│   └── vastu_agent.py      # Vastu Shastra compliance
├── algorithms/             # Layout & Evaluation Algorithms
│   ├── adjacency_solver.py # Room placement & adjacency optimization
│   └── scoring.py          # 7-axis XAI scoring system
├── data/                   # Configuration & Standards
│   ├── nbc_standards.py    # National Building Code rules
│   └── tn_setbacks.py      # Tamil Nadu specific building rules
├── validators/             # Compliance & validation logic
├── requirements.txt        # Project dependencies
└── README.md               # Project documentation
```

---

## 🔑 Key Features

### 🌍 Tamil Nadu Climate Intelligence
Automatically adjusts designs based on 4 distinct TN climate zones:
- **Coastal** (Chennai, Pondicherry) — Hot Humid focus.
- **Inland Semi-Arid** (Madurai, Salem) — Hot Dry mitigation.
- **Hilly** (Ooty, Kodaikanal) — Temperate Cool preservation.
- **Western Ghats** (Coimbatore) — Hot Humid Wet adaptation.

### 🍃 Laurie Baker Principles (Sustainable Design)
- **Rat-Trap Bond**: Thermal efficiency via wall cavity logic.
- **Jali Screens**: Natural ventilation and diffused lighting.
- **Filler Slabs**: Material conservation in RCC structures.
- **Cross-ventilation**: Computational fluid dynamics inspired window placement.

### 🧠 Explainable AI (XAI) Scoring
The system evaluates and explains designs across **7 critical axes**:
1. **Space Efficiency**: Optimization of usable vs. total area.
2. **Aspect Ratio**: Visual and functional quality of room shapes.
3. **Natural Ventilation**: Effectiveness of window placements.
4. **Climate Responsiveness**: Alignment with local environmental data.
5. **Vastu Compliance**: Traditional orientation and placement rules.
6. **NBC Compliance**: Safety, sizing, and setback standards.
7. **Circulation Quality**: Ease of movement between functional zones.

---

## 🏠 Supported Layouts
- **1BHK / 2BHK / 3BHK / 4BHK**
- **Traditional Courtyard Houses** (Tamil Nadu style)
- **Office Integrated Residential Units**
- **Vastu-aligned orientations** (North, South, East, West entry)

---

## 📝 Research Contribution
This project bridge the gap between **traditional architectural wisdom** (Laurie Baker, Vastu) and **modern computational design**. By making intuitive principles *quantifiable and explainable*, it provides a tool for sustainable, code-compliant, and culturally relevant urban housing in Tamil Nadu.

---

## 🛠️ Built With
- **Python**: Core logic and data processing.
- **Streamlit**: Interactive user interface.
- **Matplotlib**: High-fidelity architectural rendering.
- **Shapely**: Geometric operations and collision detection.
- **Pandas/NumPy**: Data handling and climate analysis.
