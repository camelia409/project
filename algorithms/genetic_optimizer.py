"""
algorithms/genetic_optimizer.py
────────────────────────────────────────────────────────────────────────────
Genetic algorithm that evolves floor-plan layout parameters and selects the
highest-scoring variant according to the existing 7-metric scoring system.

Individual gene = {col_ratios, row_ratios, corridor_depth, room_order}
Fitness         = fp.scores["Overall"]  (0–100)
Population      = 20 individuals
Generations     = 15  (~8 s wall-clock for a 12×15 m 3BHK run)
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Callable, List, Optional, Tuple

import numpy as np

# ── Constants ─────────────────────────────────────────────────────────────────

POPULATION_SIZE = 20
GENERATIONS     = 15
MUTATION_RATE   = 0.15
ELITE_COUNT     = 3        # top individuals carried unchanged to next generation

Individual = dict          # type alias for readability


# ── Seed derivation ───────────────────────────────────────────────────────────

def _individual_to_seed(individual: Individual) -> int:
    """
    Deterministically map an individual's numeric genes to an integer seed.
    Quantises each ratio to 1/1000 resolution so close-but-different individuals
    still get distinct seeds, while identical individuals always reuse the same
    cached floor-plan.
    """
    vals = individual["col_ratios"] + individual["row_ratios"] + [individual["corridor_depth"]]
    key  = tuple(round(v * 1000) for v in vals)
    return abs(hash(key)) % (2 ** 31)


# ── Individual initialisation ─────────────────────────────────────────────────

def _random_individual(n_cols: int, n_rows: int,
                        room_types: List[str], usable_h: float) -> Individual:
    """
    Generate one random but structurally valid individual.

    col_ratios   — each column ≥ 0.20, sums to 1.0
    row_ratios   — corridor fixed at corridor_pos=1; content rows fill the rest
    room_order   — identity permutation (shuffled only on mutation)
    """
    # Column ratios via symmetric Dirichlet; clip low end to avoid slivers
    cols = np.random.dirichlet(np.ones(n_cols))
    cols = np.clip(cols, 0.20, 0.55)
    cols = cols / cols.sum()

    # Corridor depth as fraction of total row height budget
    corridor_d = random.uniform(0.07, 0.10)
    remaining  = 1.0 - corridor_d

    n_content = max(n_rows - 1, 1)
    rows_base  = np.random.dirichlet(np.ones(n_content)) * remaining

    # Insert corridor after the public zone (position 1)
    corridor_pos = 1
    rows_final   = np.insert(rows_base, corridor_pos, corridor_d)

    return {
        "col_ratios":    cols.tolist(),
        "row_ratios":    rows_final.tolist(),
        "corridor_depth": corridor_d,
        "room_order":    list(range(len(room_types))),
    }


# ── Genetic operators ─────────────────────────────────────────────────────────

def _crossover(parent1: Individual, parent2: Individual) -> Individual:
    """
    Single-point crossover on col_ratios; row_ratios are inherited whole from
    the fitter parent (parent1) to preserve corridor-position integrity.
    """
    child = deepcopy(parent1)

    # Crossover col_ratios at a random split point
    n  = len(parent1["col_ratios"])
    pt = random.randint(1, n - 1)
    mixed = parent1["col_ratios"][:pt] + parent2["col_ratios"][pt:]
    s = sum(mixed)
    child["col_ratios"] = [x / s for x in mixed]

    return child


def _mutate(individual: Individual,
            mutation_rate: float = MUTATION_RATE) -> Individual:
    """
    Perturbation operators:
      • col_ratios   — swap a delta between two randomly chosen columns
      • corridor_depth — resample uniformly in [0.07, 0.10]
      • room_order   — swap two positions (rarely; affects solver tie-breaking)
    """
    ind = deepcopy(individual)

    # ── Column ratio perturbation ─────────────────────────────────────────────
    if random.random() < mutation_rate:
        cols = ind["col_ratios"]
        i    = random.randint(0, len(cols) - 1)
        j    = random.randint(0, len(cols) - 1)
        if i != j:
            delta = random.uniform(0.01, 0.08)
            cols[i] = max(0.15, cols[i] - delta)
            cols[j] = min(0.60, cols[j] + delta)
            s = sum(cols)
            ind["col_ratios"] = [x / s for x in cols]

    # ── Corridor depth perturbation ───────────────────────────────────────────
    if random.random() < mutation_rate:
        new_cd   = random.uniform(0.07, 0.10)
        old_cd   = ind["corridor_depth"]
        delta_cd = new_cd - old_cd
        rows     = ind["row_ratios"]
        # Adjust corridor row in place; redistribute delta across content rows
        corridor_pos = 1  # fixed position
        if corridor_pos < len(rows):
            rows[corridor_pos] = new_cd
            content_idx = [k for k in range(len(rows)) if k != corridor_pos]
            if content_idx:
                share = -delta_cd / len(content_idx)
                for k in content_idx:
                    rows[k] = max(0.05, rows[k] + share)
                s = sum(rows)
                ind["row_ratios"]    = [r / s for r in rows]
                ind["corridor_depth"] = new_cd

    # ── Room-order swap (low-probability) ────────────────────────────────────
    if random.random() < mutation_rate * 0.4:
        order = ind["room_order"]
        if len(order) >= 2:
            a, b = random.sample(range(len(order)), 2)
            order[a], order[b] = order[b], order[a]

    return ind


# ── Fitness evaluation ────────────────────────────────────────────────────────

def _evaluate(
    individual: Individual,
    plot_w: float,
    plot_h: float,
    bhk_type: str,
    facing: str,
    climate_zone: str,
    generate_fn: Callable,
    score_fn: Callable,
) -> Tuple[float, Optional[object]]:
    """
    Materialise *individual* into a concrete floor plan and return its score.

    The individual's genes determine a deterministic seed via _individual_to_seed().
    generate_fn is called as:
        generate_fn(plot_w, plot_h, bhk_type, climate_zone, facing, seed=<int>)
    score_fn is called as:
        score_fn(fp) -> float (0–100)

    Returns (score, floor_plan); returns (0, None) on any generation error.
    """
    try:
        seed = _individual_to_seed(individual)
        fp   = generate_fn(plot_w, plot_h, bhk_type, climate_zone, facing,
                           seed=seed)
        score = score_fn(fp)
        return float(score), fp
    except Exception:
        return 0.0, None


# ── Helper: default room types per BHK ───────────────────────────────────────

def _get_room_types(bhk_type: str) -> List[str]:
    """Minimal room-type list used to size room_order; not used for layout."""
    base = bhk_type.split(" +")[0].strip()
    counts = {
        "1BHK": ["living", "kitchen", "bedroom", "bathroom", "utility"],
        "2BHK": ["living", "dining", "kitchen", "bedroom", "bedroom",
                 "bathroom", "bathroom", "utility"],
        "3BHK": ["living", "kitchen", "bedroom", "bedroom", "bedroom",
                 "bathroom", "bathroom", "utility"],
        "4BHK": ["living", "dining", "kitchen",
                 "bedroom", "bedroom", "bedroom", "bedroom",
                 "bathroom", "bathroom", "bathroom", "bathroom",
                 "utility", "pooja", "store"],
    }
    return counts.get(base, counts["2BHK"])


# ── Main entry point ──────────────────────────────────────────────────────────

def run_genetic_optimizer(
    plot_w: float,
    plot_h: float,
    bhk_type: str,
    facing: str,
    climate_zone: str,
    generate_fn: Callable,
    score_fn: Callable,
    n_cols: int = 3,
    n_rows: int = 5,
    population_size: int = POPULATION_SIZE,
    generations: int = GENERATIONS,
    progress_callback: Optional[Callable] = None,
) -> Tuple[Optional[object], float, List[Tuple[int, float, float]]]:
    """
    Run the genetic algorithm and return the best floor plan found.

    Parameters
    ----------
    plot_w, plot_h    Plot dimensions in metres.
    bhk_type          BHK string as used by engine (e.g. "3BHK + Pooja").
    facing            Cardinal direction string (e.g. "North").
    climate_zone      Full climate zone label from TN_CLIMATE_ZONES.
    generate_fn       Callable: (plot_w, plot_h, bhk, zone, facing, seed=) → FloorPlan.
    score_fn          Callable: (FloorPlan) → float in [0, 100].
    n_cols            Number of layout columns (default 3 for 12 m plots).
    n_rows            Number of layout rows including corridor (default 5).
    population_size   Individuals per generation (default 20).
    generations       Number of evolutionary generations (default 15).
    progress_callback Optional (gen, total_gens, best_score, avg_score) → None.

    Returns
    -------
    best_fp     : FloorPlan with highest score observed across all generations.
    best_score  : Float score of best_fp.
    history     : List of (generation_idx, best_score, avg_score) per generation.
    """
    random.seed(None)          # ensure different runs produce different results
    np.random.seed(None)

    room_types = _get_room_types(bhk_type)
    usable_h   = plot_h * 0.85

    # ── Initialise population ─────────────────────────────────────────────────
    population: List[Individual] = [
        _random_individual(n_cols, n_rows, room_types, usable_h)
        for _ in range(population_size)
    ]

    history:    List[Tuple[int, float, float]] = []
    best_fp     = None
    best_score  = 0.0

    for gen in range(generations):

        # ── Evaluate all individuals ──────────────────────────────────────────
        evaluated: List[Tuple[float, Individual, Optional[object]]] = []
        for ind in population:
            score, fp = _evaluate(
                ind, plot_w, plot_h, bhk_type, facing, climate_zone,
                generate_fn, score_fn,
            )
            evaluated.append((score, ind, fp))

        # Sort descending by score
        evaluated.sort(key=lambda x: x[0], reverse=True)

        gen_best = evaluated[0][0]
        gen_avg  = float(np.mean([e[0] for e in evaluated if e[0] > 0])) \
                   if any(e[0] > 0 for e in evaluated) else 0.0

        history.append((gen, gen_best, gen_avg))

        # Update global best
        if gen_best > best_score and evaluated[0][2] is not None:
            best_score = gen_best
            best_fp    = evaluated[0][2]

        if progress_callback:
            progress_callback(gen, generations, gen_best, gen_avg)

        # ── Build next generation ─────────────────────────────────────────────
        # Elite: carry top ELITE_COUNT unchanged
        new_population: List[Individual] = [
            e[1] for e in evaluated[:ELITE_COUNT]
        ]

        # Tournament selection from top half → crossover → mutate
        top_half = evaluated[: max(2, population_size // 2)]
        while len(new_population) < population_size:
            p1 = random.choice(top_half)[1]
            p2 = random.choice(top_half)[1]
            child = _crossover(p1, p2)
            child = _mutate(child, MUTATION_RATE)
            new_population.append(child)

        population = new_population

    return best_fp, best_score, history
