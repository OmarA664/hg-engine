#!/usr/bin/env python3
"""
Johto Randomizer — for hg-engine based HGSS hacks
==================================================
Randomizes wild encounters (power-matched, rare legendaries) and gives
trainers themed-but-randomized teams at vanilla difficulty.

Run from the hg-engine repo root:
    python3 tools/johto_randomizer.py --seed 12345
    python3 tools/johto_randomizer.py --no-trainers   # wilds only
    python3 tools/johto_randomizer.py --no-wilds      # trainers only

Edits data/Encounters.c and data/Trainers.c IN PLACE.
Reset any run with:  git checkout -- data/Encounters.c data/Trainers.c src/starters.c
A spoiler log is written to randomizer_spoiler_log.txt (don't read it
if you want a blind Nuzlocke!).
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

# ----------------------------------------------------------------------
# CONFIG — tune your game here
# ----------------------------------------------------------------------

# Wild Pokémon: allowed base-stat-total band relative to the mon being
# replaced. 0.85–1.25 = "similar strength, but can run a little hot".
WILD_BST_MIN = 0.85
WILD_BST_MAX = 1.25

# Chance per wild slot of being replaced by a legendary/mythical/UB
# instead of a normal pick. 0.004 = roughly a handful of legendary
# slots across the whole game — rare enough to be an event.
LEGENDARY_WILD_CHANCE = 0.004

# Surfing and fishing slots only roll Water-types (keeps the world sane).
WATER_SLOTS_STAY_WATER = True

# Trainers: tighter band = closer to vanilla difficulty.
TRAINER_BST_MIN = 0.90
TRAINER_BST_MAX = 1.10

# Trainer picks must share at least one type with the mon they replace.
# This is what keeps Falkner a bird guy and Bugsy a bug guy.
TRAINER_KEEP_TYPE_THEME = True

# Starters: "official" = the 27 canonical starters (Imperium's roster),
# "wild" = any Pokémon of starter-grade strength (BST 280-340).
RANDOMIZE_STARTERS = True
STARTER_POOL = "official"
STARTER_KEEP_TRIANGLE = True   # guarantee one Grass, one Fire, one Water
STARTER_WILD_BST = (280, 340)

OFFICIAL_STARTERS = {
    "TYPE_GRASS": ["SPECIES_BULBASAUR", "SPECIES_CHIKORITA", "SPECIES_TREECKO",
                   "SPECIES_TURTWIG", "SPECIES_SNIVY", "SPECIES_CHESPIN",
                   "SPECIES_ROWLET", "SPECIES_GROOKEY", "SPECIES_SPRIGATITO"],
    "TYPE_FIRE":  ["SPECIES_CHARMANDER", "SPECIES_CYNDAQUIL", "SPECIES_TORCHIC",
                   "SPECIES_CHIMCHAR", "SPECIES_TEPIG", "SPECIES_FENNEKIN",
                   "SPECIES_LITTEN", "SPECIES_SCORBUNNY", "SPECIES_FUECOCO"],
    "TYPE_WATER": ["SPECIES_SQUIRTLE", "SPECIES_TOTODILE", "SPECIES_MUDKIP",
                   "SPECIES_PIPLUP", "SPECIES_OSHAWOTT", "SPECIES_FROAKIE",
                   "SPECIES_POPPLIO", "SPECIES_SOBBLE", "SPECIES_QUAXLY"],
}

# Soul Link: how tightly Player B's linked mon matches Player A's.
SOUL_LINK_BST = (0.90, 1.10)

# Species name substrings that are battle-only / unobtainable forms and
# should never appear in the wild or on trainers.
EXCLUDE_PATTERNS = [
    "_MEGA", "MEGA_", "_GIGANTAMAX", "_GMAX", "_PRIMAL", "_ORIGIN",
    "_THERIAN", "_ETERNAMAX", "_ULTRA", "_CROWNED", "_ZEN", "_SCHOOL",
    "_COMPLETE", "_TOTEM", "_CAP", "_COSPLAY", "_BUSTED", "_ASH",
    "_BATTLE_BOND", "_STARTER", "_PARTNER", "_EGG",
]
EXCLUDE_EXACT = {"SPECIES_NONE", "SPECIES_EGG", "SPECIES_BAD_EGG"}

# Base legendary / mythical / ultra beast species. These are pulled out
# of the normal pool and only appear via LEGENDARY_WILD_CHANCE.
SPECIAL_BASE_NAMES = [
    "ARTICUNO", "ZAPDOS", "MOLTRES", "MEWTWO", "MEW",
    "RAIKOU", "ENTEI", "SUICUNE", "LUGIA", "HO_OH", "CELEBI",
    "REGIROCK", "REGICE", "REGISTEEL", "LATIAS", "LATIOS",
    "KYOGRE", "GROUDON", "RAYQUAZA", "JIRACHI", "DEOXYS",
    "UXIE", "MESPRIT", "AZELF", "DIALGA", "PALKIA", "HEATRAN",
    "REGIGIGAS", "GIRATINA", "CRESSELIA", "PHIONE", "MANAPHY",
    "DARKRAI", "SHAYMIN", "ARCEUS",
    "VICTINI", "COBALION", "TERRAKION", "VIRIZION", "TORNADUS",
    "THUNDURUS", "LANDORUS", "RESHIRAM", "ZEKROM", "KYUREM",
    "KELDEO", "MELOETTA", "GENESECT",
    "XERNEAS", "YVELTAL", "ZYGARDE", "DIANCIE", "HOOPA", "VOLCANION",
    "TYPE_NULL", "SILVALLY", "TAPU_KOKO", "TAPU_LELE", "TAPU_BULU",
    "TAPU_FINI", "COSMOG", "COSMOEM", "SOLGALEO", "LUNALA", "NECROZMA",
    "MAGEARNA", "MARSHADOW", "ZERAORA", "MELTAN", "MELMETAL",
    "NIHILEGO", "BUZZWOLE", "PHEROMOSA", "XURKITREE", "CELESTEELA",
    "KARTANA", "GUZZLORD", "POIPOLE", "NAGANADEL", "STAKATAKA",
    "BLACEPHALON",
    "ZACIAN", "ZAMAZENTA", "ETERNATUS", "KUBFU", "URSHIFU", "ZARUDE",
    "REGIELEKI", "REGIDRAGO", "GLASTRIER", "SPECTRIER", "CALYREX",
    "ENAMORUS",
    "WO_CHIEN", "CHIEN_PAO", "TING_LU", "CHI_YU", "KORAIDON",
    "MIRAIDON", "WALKING_WAKE", "IRON_LEAVES", "OKIDOGI", "MUNKIDORI",
    "FEZANDIPITI", "OGERPON", "TERAPAGOS", "PECHARUNT",
]

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
SPECIES_C = REPO / "data" / "Species.c"
ENCOUNTERS_C = REPO / "data" / "Encounters.c"
TRAINERS_C = REPO / "data" / "Trainers.c"
LEARNSETS_JSON = REPO / "data" / "learnsets" / "learnsets.json"
SPECIES_H = REPO / "include" / "constants" / "species.h"
STARTERS_C = REPO / "src" / "starters.c"
LOG = REPO / "randomizer_spoiler_log.txt"

WATER_FIELDS = {"surfSlots", "oldRodSlots", "goodRodSlots", "superRodSlots"}
LAND_FIELDS = {"speciesMorning", "speciesDay", "speciesNight",
               "hoennSoundSpecies", "sinnohSoundSpecies"}


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------
def parse_species():
    """Return {SPECIES_NAME: {"bst": int, "types": set}} from Species.c."""
    text = SPECIES_C.read_text(encoding="utf-8", errors="replace")
    species = {}
    blocks = re.split(r"\n    \[(SPECIES_\w+)\] = \{", text)
    # blocks: [prefix, name1, body1, name2, body2, ...]
    for i in range(1, len(blocks) - 1, 2):
        name, body = blocks[i], blocks[i + 1]
        stats = re.search(
            r"\.hp = (\d+),\s*"
            r"\.attack = (\d+),\s*"
            r"\.defense = (\d+),\s*"
            r"\.spAttack = (\d+),\s*"
            r"\.spDefense = (\d+),\s*"
            r"\.speed = (\d+),", body)
        types = re.search(r"\.types = \{ (TYPE_\w+), (TYPE_\w+) \}", body)
        if not stats or not types:
            continue
        bst = sum(int(x) for x in stats.groups())
        species[name] = {"bst": bst, "types": {types.group(1), types.group(2)}}
    return species


def is_excluded(name):
    if name in EXCLUDE_EXACT:
        return True
    return any(p in name for p in EXCLUDE_PATTERNS)


def build_pools(species):
    special_exact = {f"SPECIES_{n}" for n in SPECIAL_BASE_NAMES}
    normal, special = {}, {}
    for name, info in species.items():
        if is_excluded(name):
            continue
        if name in special_exact:
            special[name] = info
        elif any(base in name for base in SPECIAL_BASE_NAMES):
            # a form of a legendary (e.g. KYUREM_WHITE) — skip entirely
            continue
        else:
            normal[name] = info
    return normal, special


# ----------------------------------------------------------------------
# Picking
# ----------------------------------------------------------------------
def pick(rng, pool, orig_bst, lo, hi, need_types=None, widen=0.05, tries=5):
    """Pick a species from pool with BST in [orig*lo, orig*hi], optionally
    sharing a type. Widens the band if nothing fits, then drops the band."""
    names = list(pool)
    for step in range(tries + 1):
        a = orig_bst * (lo - widen * step)
        b = orig_bst * (hi + widen * step)
        cands = [n for n in names
                 if a <= pool[n]["bst"] <= b
                 and (not need_types or pool[n]["types"] & need_types)]
        if cands:
            return rng.choice(cands)
    if need_types:
        cands = [n for n in names if pool[n]["types"] & need_types]
        if cands:
            return rng.choice(cands)
    return rng.choice(names)


# ----------------------------------------------------------------------
# Encounters
# ----------------------------------------------------------------------
def randomize_encounters(rng, normal, special, species, log,
                         rng_b=None, player=None, pairs=None):
    text = ENCOUNTERS_C.read_text(encoding="utf-8", errors="replace")
    out, field, area = [], None, "?"
    n_changed = n_legend = 0

    triple = re.compile(r"(\{\s*\d+,\s*\d+,\s*)(SPECIES_\w+)(\s*\})")
    lone = re.compile(r"^(\s*)(SPECIES_\w+)(,\s*)$")

    def replace(orig, water_ok):
        nonlocal n_changed, n_legend
        if orig == "SPECIES_NONE" or orig not in species:
            return orig
        obst = species[orig]["bst"]
        need = {"TYPE_WATER"} if water_ok else None
        # Player A's pick (also the solo pick) — always computed the same
        # way so both players' generators stay in perfect sync.
        if rng.random() < LEGENDARY_WILD_CHANCE and special:
            a_new = rng.choice(sorted(special))
        else:
            a_new = pick(rng, normal, obst, WILD_BST_MIN, WILD_BST_MAX, need)
        result = a_new
        if rng_b is not None:
            # Player B's pick: a partner power-matched to A's mon.
            # Legendary slots pair legendary-with-legendary.
            if a_new in special:
                b_new = rng_b.choice(sorted(special))
            else:
                b_new = pick(rng_b, normal, species[a_new]["bst"],
                             SOUL_LINK_BST[0], SOUL_LINK_BST[1], need)
            pairs.append(f"  [{area}] {field}: A={a_new}  <->  B={b_new}")
            if player == "B":
                result = b_new
        if result in special:
            n_legend += 1
        if result != orig:
            n_changed += 1
            log.append(f"  [{area}] {field}: {orig} -> {result}")
        return result

    for line in text.splitlines(keepends=True):
        m = re.search(r"\[(ENCDATA_\w+)\] = \{", line)
        if m:
            area = m.group(1)
        m = re.search(r"\.(\w+) = \{", line)
        if m and m.group(1) not in ("landSlots",):
            field = m.group(1)

        if field in LAND_FIELDS:
            m = lone.match(line)
            if m:
                new = replace(m.group(2), water_ok=False)
                line = f"{m.group(1)}{new}{m.group(3)}"
        elif field in WATER_FIELDS or field == "rockSmashSlots":
            water = WATER_SLOTS_STAY_WATER and field in WATER_FIELDS
            line = triple.sub(
                lambda m: m.group(1) + replace(m.group(2), water) + m.group(3),
                line)
        out.append(line)

    ENCOUNTERS_C.write_text("".join(out), encoding="utf-8")
    return n_changed, n_legend


# ----------------------------------------------------------------------
# Trainers
# ----------------------------------------------------------------------
def last_four_moves(learnsets, name, level):
    entry = learnsets.get(name)
    if not entry:
        return None
    moves, seen = [], set()
    for lm in entry.get("LevelMoves", []):
        if lm["Level"] <= level and lm["Move"] not in seen:
            moves.append(lm["Move"])
            seen.add(lm["Move"])
    moves = moves[-4:] if moves else ["MOVE_TACKLE"]
    while len(moves) < 4:
        moves.append("MOVE_NONE")
    return moves


def party_themes(text, species):
    """Pass 1: for each party (in file order), find its dominant type.
    Uses the exact same brace-walking as the replacement pass, so the
    two passes can never fall out of alignment. Ties drop TYPE_NORMAL
    when possible — a bird gym is Flying, not Normal."""
    themes = []
    in_party = False
    depth = depth_at_party = 0
    counts = {}

    def close():
        if not counts:
            themes.append(None)
            return
        best = max(counts.values())
        top = sorted(t for t, c in counts.items() if c == best)
        non_normal = [t for t in top if t != "TYPE_NORMAL"]
        themes.append({(non_normal or top)[0]})

    for line in text.splitlines():
        if ".party = {" in line:
            in_party = True
            depth_at_party = depth
            counts = {}
        depth += line.count("{") - line.count("}")
        if in_party and depth <= depth_at_party:
            in_party = False
            close()
            continue
        if in_party:
            m = re.search(r"\.species = (SPECIES_\w+)", line)
            if m:
                for t in species.get(m.group(1), {}).get("types", ()):
                    counts[t] = counts.get(t, 0) + 1
    return themes


def randomize_trainers(rng, normal, species, learnsets, log):
    text = TRAINERS_C.read_text(encoding="utf-8", errors="replace")
    # trainer pool: normal mons that have learnset data (so movesets work)
    pool = {n: v for n, v in normal.items() if n in learnsets}
    themes = party_themes(text, species)
    party_i = -1

    lines = text.splitlines(keepends=True)
    out = []
    in_party = False
    depth_at_party = 0
    depth = 0
    cur_level = 5
    cur_new = None
    name = "?"
    n_mons = 0

    for line in lines:
        m = re.search(r'\.name = "([^"]*)"', line)
        if m:
            name = m.group(1)
        if ".party = {" in line:
            in_party = True
            party_i += 1
            used = set()
            depth_at_party = depth
        depth += line.count("{") - line.count("}")
        if in_party and depth <= depth_at_party:
            in_party = False

        if in_party:
            m = re.search(r"\.level = (\d+)", line)
            if m:
                cur_level = int(m.group(1))
            m = re.search(r"(\s*\.species = )(SPECIES_\w+)(,)", line)
            if m and m.group(2) in species:
                orig = m.group(2)
                need = None
                if TRAINER_KEEP_TYPE_THEME:
                    need = (themes[party_i] if 0 <= party_i < len(themes)
                            and themes[party_i] else species[orig]["types"])
                subpool = {n: v for n, v in pool.items() if n not in used}
                cur_new = pick(rng, subpool or pool, species[orig]["bst"],
                               TRAINER_BST_MIN, TRAINER_BST_MAX, need)
                used.add(cur_new)
                n_mons += 1
                log.append(f"  {name}: Lv{cur_level} {orig} -> {cur_new}")
                line = f"{m.group(1)}{cur_new}{m.group(3)}\n"
            m = re.search(r"^(\s*)\.moves = \{.*\},\s*$", line)
            if m and cur_new:
                mv = last_four_moves(learnsets, cur_new, cur_level)
                line = f"{m.group(1)}.moves = {{ {', '.join(mv)} }},\n"
        out.append(line)

    TRAINERS_C.write_text("".join(out), encoding="utf-8")
    return n_mons


# ----------------------------------------------------------------------
# Starters
# ----------------------------------------------------------------------
def randomize_starters(rng, normal, species, log):
    if STARTER_POOL == "official":
        if STARTER_KEEP_TRIANGLE:
            picks = [rng.choice(OFFICIAL_STARTERS[t])
                     for t in ("TYPE_GRASS", "TYPE_FIRE", "TYPE_WATER")]
        else:
            allofficial = sum(OFFICIAL_STARTERS.values(), [])
            picks = rng.sample(allofficial, 3)
    else:  # "wild"
        lo, hi = STARTER_WILD_BST
        tier = {n: v for n, v in normal.items() if lo <= v["bst"] <= hi}
        if STARTER_KEEP_TRIANGLE:
            picks = []
            for t in ("TYPE_GRASS", "TYPE_FIRE", "TYPE_WATER"):
                cands = [n for n, v in tier.items()
                         if t in v["types"] and n not in picks]
                picks.append(rng.choice(cands or list(tier)))
        else:
            picks = rng.sample(list(tier), 3)

    rng.shuffle(picks)  # ball positions stay a mystery
    text = STARTERS_C.read_text(encoding="utf-8", errors="replace")
    new_block = ("static const u16 sStarterChoices[3] = {\n"
                 f"    {picks[0]},\n    {picks[1]},\n    {picks[2]},\n}};")
    text, n = re.subn(
        r"static const u16 sStarterChoices\[3\] = \{.*?\};",
        new_block, text, count=1, flags=re.S)
    if n != 1:
        print("WARNING: could not find sStarterChoices in starters.c")
        return False
    STARTERS_C.write_text(text, encoding="utf-8")
    log.append("")
    log.append("== STARTERS (left, middle, right) ==")
    for p in picks:
        log.append(f"  {p}")
    return True


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------
def validate(paths):
    valid = set(re.findall(r"#define (SPECIES_\w+)",
                           SPECIES_H.read_text(errors="replace")))
    bad = set()
    for p in paths:
        text = p.read_text(errors="replace")
        text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
        for tok in re.findall(r"SPECIES_\w+", text):
            if tok not in valid:
                bad.add(tok)
    return bad


# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--no-wilds", action="store_true")
    ap.add_argument("--no-trainers", action="store_true")
    ap.add_argument("--no-starters", action="store_true")
    ap.add_argument("--soul-link", choices=["A", "B"], default=None,
                    help="generate one half of a Soul Link pair; your "
                         "partner runs the SAME seed with the other letter")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else random.randrange(10**9)
    rng = random.Random(seed)
    rng_b = random.Random(f"{seed}-soullink") if args.soul_link else None
    pairs = [f"Soul Link pair chart — seed {seed}",
             "Identical for both players. Spoilers by nature!", ""]
    print(f"Seed: {seed}  (re-run with --seed {seed} to reproduce)")
    if args.soul_link:
        other = "B" if args.soul_link == "A" else "A"
        print(f"Soul Link: this is Player {args.soul_link}'s world. "
              f"Your partner runs the same seed with --soul-link {other}.")

    species = parse_species()
    normal, special = build_pools(species)
    learnsets = json.loads(LEARNSETS_JSON.read_text(errors="replace"))
    print(f"Parsed {len(species)} species "
          f"({len(normal)} in normal pool, {len(special)} legendary pool)")

    log = [f"Johto Randomizer spoiler log — seed {seed}", ""]

    if not args.no_wilds:
        log.append("== WILD ENCOUNTERS ==")
        n, nl = randomize_encounters(rng, normal, special, species, log,
                                     rng_b=rng_b, player=args.soul_link,
                                     pairs=pairs)
        print(f"Wilds: {n} slots randomized, {nl} legendary slots placed")
        if args.soul_link:
            (REPO / "soul_link_pairs.txt").write_text(
                "\n".join(pairs), encoding="utf-8")
            print("Linked-pair chart: soul_link_pairs.txt "
                  "(same file for both players)")

    if not args.no_trainers:
        log.append("")
        log.append("== TRAINERS ==")
        n = randomize_trainers(rng, normal, species, learnsets, log)
        print(f"Trainers: {n} party members randomized (levels/items/AI untouched)")

    if RANDOMIZE_STARTERS and not args.no_starters:
        if randomize_starters(rng, normal, species, log):
            print("Starters: 3 mystery balls set (no spoilers here — "
                  "the log knows, the ball text will still lie)")

    bad = validate([ENCOUNTERS_C, TRAINERS_C, STARTERS_C])
    if bad:
        print("WARNING: unknown species emitted:", sorted(bad)[:10])
        sys.exit(1)
    print("Validation passed: every emitted species exists in species.h")

    LOG.write_text("\n".join(log), encoding="utf-8")
    print(f"Spoiler log: {LOG.name} (avoid reading for a blind run!)")


if __name__ == "__main__":
    main()
