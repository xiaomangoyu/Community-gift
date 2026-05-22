"""Generate synthetic streamer signal folders for image2 reference-library tests.

The generated data is intentionally separate from real ``streamers/`` data:

    streamers_synthetic/image2_reference_200/<fake_anchor_id>_<name>/signals.md

All generated source text is ASCII/English-only so the batch can test broad
visual coverage without adding Chinese or multilingual typography pressure.
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "streamers_synthetic" / "image2_reference_200"
ANCHOR_BASE = 910000000000000000


VARIANTS = [
    {
        "code": "core",
        "label": "Core",
        "mode": "baseline",
        "score": "0",
        "focus": "balanced readable silhouette, clean collector product proportions",
        "signals": ["balanced_silhouette", "reference_core_case"],
    },
    {
        "code": "sculpt",
        "label": "Sculpt",
        "mode": "expressive",
        "score": "1",
        "focus": "more dimensional lamp head relief and clearer front-to-side volume",
        "signals": ["sculptural_form_case", "clear_3d_volume"],
    },
    {
        "code": "edge",
        "label": "Edge",
        "mode": "expressive",
        "score": "2",
        "focus": "stronger rim light, sharper edge readability, controlled highlight contrast",
        "signals": ["rim_light_case", "edge_light_case"],
    },
    {
        "code": "handle",
        "label": "Handle",
        "mode": "expressive",
        "score": "2",
        "focus": "personalized handle connection, motif embedded into the neck and grip",
        "signals": ["handle_integration_case", "motif_on_handle"],
    },
    {
        "code": "wild",
        "label": "Wild",
        "mode": "wild",
        "score": "3",
        "focus": "the broadest silhouette variation while keeping a product-like lightstick",
        "signals": ["silhouette_range_case", "high_variation_case"],
    },
]


ARCHETYPES = [
    {
        "name": "Nova Fox",
        "club": "Moon Crew",
        "family": "moonlit mask idol",
        "symbols": ["fox mask", "crescent moon", "ribbon tail"],
        "palette": ["black", "silver", "lilac"],
        "materials": ["pearl enamel", "smoked crystal", "soft vinyl"],
        "vibe": ["dreamy", "glamorous", "designer_toy"],
        "form": "crescent mask lamp head with swept cheek fins and a tucked ribbon tail",
        "axes": ["claw", "luxury"],
    },
    {
        "name": "Luna Moth",
        "club": "Glow Wing",
        "family": "soft wing night garden",
        "symbols": ["moth wing", "moon pearl", "antenna arc"],
        "palette": ["cream", "mint", "pale gold"],
        "materials": ["frosted crystal", "pearl coating", "translucent jelly"],
        "vibe": ["soft", "dreamy", "romantic"],
        "form": "rounded wing lamp head with soft antenna arcs and a pearl center",
        "axes": ["feather"],
    },
    {
        "name": "Pixel Cat",
        "club": "Bit Pals",
        "family": "cute arcade mascot",
        "symbols": ["cat ear", "pixel star", "game button"],
        "palette": ["cyan", "pink", "white"],
        "materials": ["glossy resin", "soft vinyl", "clear acrylic"],
        "vibe": ["playful", "designer_toy", "sweet"],
        "form": "rounded cat-ear core with tiny pixel star corners and soft game-button nodes",
        "axes": ["lightning"],
    },
    {
        "name": "Atlas Comet",
        "club": "Star Run",
        "family": "cosmic racer",
        "symbols": ["comet", "star trail", "orbit ring"],
        "palette": ["deep blue", "silver", "electric pink"],
        "materials": ["frosted crystal", "mirror trim", "translucent resin"],
        "vibe": ["battle", "bold", "idol_support"],
        "form": "comet-shaped lamp head with an orbit ring folded into the edge",
        "axes": ["lightning", "spike"],
    },
    {
        "name": "Coral Muse",
        "club": "Reef Pop",
        "family": "ocean pop performer",
        "symbols": ["coral branch", "shell pearl", "wave curl"],
        "palette": ["coral", "aqua", "pearl white"],
        "materials": ["pearl enamel", "clear resin", "jelly coating"],
        "vibe": ["sweet", "elegant", "playful"],
        "form": "rounded shell core framed by coral branch curls and wave pads",
        "axes": ["crest"],
    },
    {
        "name": "Velvet Crown",
        "club": "Royal Beat",
        "family": "stage royalty",
        "symbols": ["crown", "velvet bow", "stage gem"],
        "palette": ["ruby red", "gold", "black"],
        "materials": ["velvet matte coating", "polished enamel", "gem resin"],
        "vibe": ["glamorous", "luxury_collectible", "elegant"],
        "form": "puffed crown lamp head with low rounded points and inset gem pads",
        "axes": ["crest", "luxury"],
    },
    {
        "name": "Cherry Pop",
        "club": "Pop Duo",
        "family": "fruit candy idol",
        "symbols": ["cherry pair", "leaf cap", "bubble bead"],
        "palette": ["cherry red", "candy pink", "mint"],
        "materials": ["glossy resin", "translucent jelly", "soft enamel"],
        "vibe": ["sweet", "playful", "designer_toy"],
        "form": "double cherry lamp head with a soft leaf cap and bubble-bead rim",
        "axes": [],
    },
    {
        "name": "Mint Melon",
        "club": "Fresh Bite",
        "family": "fresh soda mascot",
        "symbols": ["melon slice", "soda bubble", "leaf stripe"],
        "palette": ["mint green", "lime", "cream"],
        "materials": ["jelly resin", "pearl plastic", "soft vinyl"],
        "vibe": ["sweet", "soft", "playful"],
        "form": "rounded melon-slice head with bubble nodes and a leaf-striped handle neck",
        "axes": [],
    },
    {
        "name": "Aurora Bunny",
        "club": "Soft Hop",
        "family": "pastel aurora mascot",
        "symbols": ["bunny ear", "aurora ribbon", "cloud puff"],
        "palette": ["lavender", "pink", "icy blue"],
        "materials": ["frosted resin", "pearl coating", "soft vinyl"],
        "vibe": ["dreamy", "soft", "sweet"],
        "form": "egg-shaped core with low bunny-ear arcs and aurora ribbon wrap",
        "axes": ["feather"],
    },
    {
        "name": "Raven Vow",
        "club": "Black Wing",
        "family": "dark feather glam",
        "symbols": ["raven feather", "black wing", "silver bead"],
        "palette": ["black", "graphite", "silver"],
        "materials": ["matte graphite", "mirror metal", "fiber feather"],
        "vibe": ["edgy", "glamorous", "wild"],
        "form": "teardrop lamp head with layered feather fins and a silver bead core",
        "axes": ["feather", "rock_glam"],
    },
    {
        "name": "Thunder Arcade",
        "club": "Bolt Team",
        "family": "high-energy arcade",
        "symbols": ["lightning", "arcade button", "score star"],
        "palette": ["yellow", "electric blue", "black"],
        "materials": ["glossy resin", "clear acrylic", "rubber-soft matte accents"],
        "vibe": ["battle", "playful", "bold"],
        "form": "rounded bolt lamp head with button-like corner nodes and a star core",
        "axes": ["lightning"],
    },
    {
        "name": "Lotus Drift",
        "club": "Calm Bloom",
        "family": "serene botanical",
        "symbols": ["lotus petal", "water drop", "halo ring"],
        "palette": ["pale pink", "jade green", "pearl white"],
        "materials": ["frosted crystal", "pearl enamel", "clear resin"],
        "vibe": ["soft", "elegant", "romantic"],
        "form": "layered lotus-petal head with a water-drop core and shallow halo rim",
        "axes": ["crest"],
    },
    {
        "name": "Pearl Shell",
        "club": "Shell Club",
        "family": "clean coastal pearl",
        "symbols": ["shell", "pearl", "wave ridge"],
        "palette": ["pearl white", "aqua", "champagne"],
        "materials": ["pearl coating", "opal resin", "soft enamel"],
        "vibe": ["elegant", "soft", "luxury_collectible"],
        "form": "fan shell lamp head with raised wave ridges and a pearl center",
        "axes": ["luxury"],
    },
    {
        "name": "Crystal Drake",
        "club": "Scale Light",
        "family": "fantasy crystal guardian",
        "symbols": ["dragon scale", "crystal horn", "glow ember"],
        "palette": ["emerald", "silver", "violet"],
        "materials": ["cut crystal", "scale texture", "smoked resin"],
        "vibe": ["wild", "bold", "luxury_collectible"],
        "form": "oval crystal core with shallow scale relief and small horn arcs",
        "axes": ["scale", "horn", "spike"],
    },
    {
        "name": "Boxing Star",
        "club": "Round Win",
        "family": "sport battle cheer",
        "symbols": ["boxing glove", "victory star", "belt badge"],
        "palette": ["red", "white", "gold"],
        "materials": ["soft leather wrap", "gloss enamel", "pearl plastic"],
        "vibe": ["battle", "bold", "playful"],
        "form": "puffed glove lamp head with star badge core and rounded belt side tabs",
        "axes": ["combat"],
    },
    {
        "name": "Sunflower Bee",
        "club": "Sunny Hive",
        "family": "warm garden mascot",
        "symbols": ["sunflower", "bee wing", "honey drop"],
        "palette": ["sun yellow", "warm brown", "cream"],
        "materials": ["soft enamel", "translucent honey resin", "pearl coating"],
        "vibe": ["sweet", "playful", "soft"],
        "form": "sunflower disk head with petal cushions and small wing side pads",
        "axes": ["feather"],
    },
    {
        "name": "Snow Swan",
        "club": "White Lake",
        "family": "icy elegant wing",
        "symbols": ["swan wing", "snowflake", "ice drop"],
        "palette": ["white", "icy blue", "silver"],
        "materials": ["frosted crystal", "pearl enamel", "mirror trim"],
        "vibe": ["elegant", "dreamy", "soft"],
        "form": "swan-wing lamp head with a snowflake core and ice-drop bottom node",
        "axes": ["feather"],
    },
    {
        "name": "Neon Skater",
        "club": "Rail Glow",
        "family": "street pop motion",
        "symbols": ["skate wheel", "neon stripe", "spark star"],
        "palette": ["lime", "hot pink", "graphite"],
        "materials": ["matte graphite", "gloss resin", "clear acrylic"],
        "vibe": ["edgy", "playful", "bold"],
        "form": "skate-wheel oval with diagonal neon stripe fins and small spark nodes",
        "axes": ["lightning", "rock_glam"],
    },
    {
        "name": "Gothic Rose",
        "club": "Rose Noir",
        "family": "dark romantic floral",
        "symbols": ["rose bloom", "thorn arc", "black ribbon"],
        "palette": ["black", "wine red", "silver"],
        "materials": ["velvet matte coating", "mirror trim", "deep resin"],
        "vibe": ["romantic", "edgy", "glamorous"],
        "form": "rose-bloom lamp head with rounded thorn arcs and black ribbon neck",
        "axes": ["spike", "rock_glam"],
    },
    {
        "name": "Glass Jelly",
        "club": "Drift Glow",
        "family": "transparent ocean creature",
        "symbols": ["jellyfish bell", "bubble trail", "soft tentacle curve"],
        "palette": ["clear aqua", "lavender", "pearl"],
        "materials": ["transparent jelly resin", "frosted crystal", "soft glow core"],
        "vibe": ["dreamy", "soft", "designer_toy"],
        "form": "jellyfish bell lamp head with short rounded flowing fins and bubble beads",
        "axes": ["feather"],
    },
    {
        "name": "Toucan Tempo",
        "club": "Tropic Pop",
        "family": "tropical music mascot",
        "symbols": ["toucan beak", "music note", "leaf fan"],
        "palette": ["orange", "teal", "black"],
        "materials": ["glossy resin", "soft enamel", "clear acrylic"],
        "vibe": ["playful", "bold", "idol_support"],
        "form": "rounded beak lamp head with leaf-fan side pads and a music-note core",
        "axes": ["feather"],
    },
    {
        "name": "Plush Bear",
        "club": "Hug Club",
        "family": "soft plush mascot",
        "symbols": ["bear ear", "heart patch", "stitch bead"],
        "palette": ["cream", "candy pink", "warm beige"],
        "materials": ["soft vinyl", "matte velvet coating", "pearl plastic"],
        "vibe": ["sweet", "soft", "designer_toy"],
        "form": "rounded bear-ear lamp head with a heart patch core and stitch-like bead rim",
        "axes": [],
    },
    {
        "name": "Synth Key",
        "club": "Key Wave",
        "family": "music tech idol",
        "symbols": ["keyboard key", "sound wave", "equalizer bar"],
        "palette": ["black", "cyan", "silver"],
        "materials": ["mirror trim", "matte graphite", "clear acrylic"],
        "vibe": ["idol_support", "edgy", "bold"],
        "form": "rounded keycap lamp head with sound-wave rim and equalizer bead accents",
        "axes": ["lightning"],
    },
    {
        "name": "Coffee Glow",
        "club": "Cafe Live",
        "family": "warm cafe chat",
        "symbols": ["coffee bean", "steam curl", "cream drop"],
        "palette": ["espresso", "cream", "champagne"],
        "materials": ["matte enamel", "pearl coating", "translucent cream resin"],
        "vibe": ["soft", "elegant", "romantic"],
        "form": "coffee-bean oval lamp head with steam curls and a cream-drop center",
        "axes": [],
    },
    {
        "name": "Tarot Sun",
        "club": "Sun Deck",
        "family": "mystic stage oracle",
        "symbols": ["sun halo", "card corner", "gold ray"],
        "palette": ["gold", "white", "deep blue"],
        "materials": ["pearl enamel", "mirror gold trim", "frosted crystal"],
        "vibe": ["elegant", "luxury_collectible", "dreamy"],
        "form": "sun-halo lamp head with soft card-corner tabs and raised ray beads",
        "axes": ["crest", "luxury"],
    },
    {
        "name": "Rain Cloud",
        "club": "Soft Rain",
        "family": "gentle weather mood",
        "symbols": ["rain cloud", "water drop", "silver lining"],
        "palette": ["sky blue", "white", "silver"],
        "materials": ["frosted resin", "pearl coating", "clear water-drop acrylic"],
        "vibe": ["soft", "dreamy", "romantic"],
        "form": "puffy cloud lamp head with water-drop bottom node and silver lining rim",
        "axes": [],
    },
    {
        "name": "Candy Rocket",
        "club": "Sugar Run",
        "family": "sweet space toy",
        "symbols": ["rocket fin", "candy stripe", "star puff"],
        "palette": ["candy pink", "white", "electric blue"],
        "materials": ["glossy resin", "soft enamel", "translucent jelly"],
        "vibe": ["playful", "sweet", "bold"],
        "form": "rounded rocket lamp head with soft fins and candy-stripe neck detail",
        "axes": ["flame", "lightning"],
    },
    {
        "name": "Flame Phoenix",
        "club": "Rise Glow",
        "family": "rebirth stage energy",
        "symbols": ["phoenix feather", "flame crest", "ember gem"],
        "palette": ["orange", "red", "gold"],
        "materials": ["glowing resin", "mirror trim", "pearl enamel"],
        "vibe": ["battle", "wild", "glamorous"],
        "form": "flame-feather lamp head with upward crest fins and an ember gem core",
        "axes": ["flame", "feather", "crest"],
    },
    {
        "name": "Chrome Wave",
        "club": "Wave Set",
        "family": "sleek dance stage",
        "symbols": ["wave crest", "chrome bead", "sound ripple"],
        "palette": ["silver", "blue", "black"],
        "materials": ["mirror metal", "smoked resin", "clear acrylic"],
        "vibe": ["glamorous", "elegant", "bold"],
        "form": "wave-crest lamp head with chrome beads and a rippled side profile",
        "axes": ["luxury"],
    },
    {
        "name": "Dice Diva",
        "club": "Lucky Six",
        "family": "lucky glam game night",
        "symbols": ["dice pip", "lucky star", "curved ribbon"],
        "palette": ["white", "black", "hot pink"],
        "materials": ["glossy enamel", "mirror trim", "soft vinyl"],
        "vibe": ["glamorous", "playful", "bold"],
        "form": "rounded dice-pip lamp head with curved ribbon corners and star core",
        "axes": ["rock_glam"],
    },
    {
        "name": "Wolf Ridge",
        "club": "Ridge Pack",
        "family": "mountain night wild",
        "symbols": ["wolf ear", "mountain ridge", "moon chip"],
        "palette": ["graphite", "ice blue", "silver"],
        "materials": ["matte graphite", "frosted crystal", "mirror trim"],
        "vibe": ["wild", "edgy", "bold"],
        "form": "shield-like rounded mountain ridge head with wolf-ear side arcs",
        "axes": ["claw", "fang", "predator"],
    },
    {
        "name": "Berry Ribbon",
        "club": "Berry Loop",
        "family": "sweet ribbon fruit",
        "symbols": ["strawberry", "ribbon loop", "seed bead"],
        "palette": ["strawberry red", "cream", "leaf green"],
        "materials": ["glossy resin", "soft enamel", "pearl plastic"],
        "vibe": ["sweet", "playful", "soft"],
        "form": "strawberry lamp head with ribbon-loop side fins and seed-bead relief",
        "axes": [],
    },
    {
        "name": "Panda Leaf",
        "club": "Bamboo Pop",
        "family": "friendly bamboo mascot",
        "symbols": ["panda ear", "bamboo leaf", "round patch"],
        "palette": ["black", "white", "bamboo green"],
        "materials": ["soft vinyl", "matte enamel", "clear green resin"],
        "vibe": ["playful", "soft", "designer_toy"],
        "form": "rounded panda-ear lamp head with bamboo leaf pads and soft patch center",
        "axes": [],
    },
    {
        "name": "Disco Prism",
        "club": "Mirror Beat",
        "family": "dance floor sparkle",
        "symbols": ["mirrorball tile", "prism flare", "music pulse"],
        "palette": ["silver", "purple", "cyan"],
        "materials": ["mirror trim", "faceted resin", "clear acrylic"],
        "vibe": ["glamorous", "idol_support", "bold"],
        "form": "rounded prism lamp head with mirrorball tile relief and pulse side nodes",
        "axes": ["luxury", "rock_glam"],
    },
    {
        "name": "Astro Star",
        "club": "Orbit One",
        "family": "space explorer charm",
        "symbols": ["astronaut helmet", "star", "orbit ring"],
        "palette": ["white", "navy", "silver"],
        "materials": ["pearl plastic", "clear visor resin", "mirror trim"],
        "vibe": ["dreamy", "playful", "idol_support"],
        "form": "rounded helmet lamp head with star core and a soft orbit-ring rim",
        "axes": ["lightning"],
    },
    {
        "name": "Kite Prism",
        "club": "Sky Loop",
        "family": "airborne festival",
        "symbols": ["kite diamond", "ribbon tail", "wind swirl"],
        "palette": ["sky blue", "coral", "white"],
        "materials": ["frosted resin", "soft enamel", "translucent ribbon acrylic"],
        "vibe": ["playful", "soft", "dreamy"],
        "form": "rounded kite-diamond lamp head with ribbon-tail grip detail and wind-swirl rim",
        "axes": ["feather"],
    },
    {
        "name": "Lace Heart",
        "club": "Love Lace",
        "family": "romantic lace idol",
        "symbols": ["heart", "lace loop", "pearl bead"],
        "palette": ["rose pink", "pearl white", "champagne"],
        "materials": ["pearl coating", "soft enamel", "frosted crystal"],
        "vibe": ["romantic", "sweet", "elegant"],
        "form": "puffed heart lamp head with lace-loop relief and pearl-bead rim",
        "axes": ["luxury"],
    },
    {
        "name": "Cactus Bloom",
        "club": "Desert Pop",
        "family": "desert cute plant",
        "symbols": ["cactus arm", "small flower", "sun bead"],
        "palette": ["sage green", "coral", "sand cream"],
        "materials": ["matte enamel", "soft vinyl", "translucent flower resin"],
        "vibe": ["playful", "soft", "sweet"],
        "form": "rounded cactus lamp head with small flower cap and sun-bead center",
        "axes": ["spike"],
    },
    {
        "name": "Quartz Halo",
        "club": "Clear Ring",
        "family": "minimal crystal premium",
        "symbols": ["quartz point", "halo ring", "light bead"],
        "palette": ["clear white", "silver", "pale violet"],
        "materials": ["frosted crystal", "mirror trim", "translucent resin"],
        "vibe": ["elegant", "luxury_collectible", "dreamy"],
        "form": "smooth halo lamp head with softened quartz points and a clear bead core",
        "axes": ["spike", "luxury"],
    },
    {
        "name": "Night Bat",
        "club": "Echo Club",
        "family": "cute dark night",
        "symbols": ["bat wing", "moon chip", "echo arc"],
        "palette": ["black", "violet", "silver"],
        "materials": ["matte graphite", "soft enamel", "smoked crystal"],
        "vibe": ["edgy", "playful", "glamorous"],
        "form": "rounded bat-wing lamp head with moon-chip core and echo-arc handle neck",
        "axes": ["feather", "rock_glam"],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate isolated synthetic signals.md data for image2 reference tests."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT),
        help="Output root for synthetic streamer folders.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=200,
        help="Number of synthetic signal folders to generate.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the output directory if it already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.count <= 0:
        raise ValueError("--count must be > 0")

    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = REPO / output_dir
    output_dir = output_dir.resolve()

    if output_dir.exists():
        if not args.overwrite:
            raise SystemExit(f"{output_dir} already exists. Use --overwrite to replace it.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    rows = build_rows(args.count)
    for index, row in enumerate(rows, start=1):
        folder = output_dir / f"{row['anchor_id']}_{slugify(row['host_name'])}"
        folder.mkdir()
        (folder / "signals.md").write_text(render_signals(row), encoding="ascii")

    (output_dir / "INDEX.md").write_text(render_index(rows), encoding="ascii")
    print(f"Generated {len(rows)} synthetic streamer signal folders: {output_dir}")


def build_rows(count: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    row_id = 0
    for archetype in ARCHETYPES:
        for variant in VARIANTS:
            row_id += 1
            if row_id > count:
                return rows
            rows.append(build_row(row_id, archetype, variant))
    while row_id < count:
        archetype = ARCHETYPES[row_id % len(ARCHETYPES)]
        variant = VARIANTS[(row_id // len(ARCHETYPES)) % len(VARIANTS)]
        row_id += 1
        rows.append(build_row(row_id, archetype, variant))
    return rows


def build_row(row_id: int, archetype: dict[str, object], variant: dict[str, object]) -> dict[str, object]:
    host_name = f"{archetype['name']} {variant['label']}"
    signals = [
        "synthetic_reference_candidate",
        "not_real_streamer",
        "english_only_source_text",
        "no_chinese_text_source",
        "generic_reference_library",
        "distinct_color_system",
        "recurring_mascot_or_object",
        "clear_material_direction",
        *archetype["vibe"],
        *variant["signals"],
    ]
    axes = list(archetype["axes"])
    return {
        "row_id": row_id,
        "anchor_id": str(ANCHOR_BASE + row_id),
        "host_name": host_name,
        "fan_club": archetype["club"],
        "family": archetype["family"],
        "symbols": archetype["symbols"],
        "palette": archetype["palette"],
        "materials": archetype["materials"],
        "vibe": archetype["vibe"],
        "form": archetype["form"],
        "mode": variant["mode"],
        "score": variant["score"],
        "focus": variant["focus"],
        "signals": dedupe(signals),
        "axes": axes,
    }


def render_signals(row: dict[str, object]) -> str:
    symbols = list(row["symbols"])
    signals = list(row["signals"])
    palette = ", ".join(row["palette"])
    materials = ", ".join(row["materials"])
    vibe = ", ".join(row["vibe"])
    axes = ", ".join(row["axes"]) if row["axes"] else "none"

    top_symbols = "\n".join(
        f"- `{symbol}` ({'comm' if index < 2 else 'host'})"
        for index, symbol in enumerate(symbols)
    )
    primary_signals = "\n".join(f"- `{signal}`" for signal in signals)

    characterization = (
        f"This is a synthetic reference-library archetype, not a real creator. "
        f"The streamer type is {row['family']}. Visual identity centers on "
        f"{symbols[0]} with {symbols[1]} as the supporting cue. Palette direction: "
        f"{palette}. Material direction: {materials}. Mood coverage: {vibe}. "
        f"The lightstick should explore {row['form']}. Variant focus: {row['focus']}. "
        "Keep visible typography simple, Latin-only, and limited to the short fan-club label. "
        "Avoid Chinese characters, dense text, real faces, weapons, and literal streamer portraits."
    )

    return f"""# {row['host_name']}

- **anchor_id**: {row['anchor_id']}
- **tier**: synthetic
- **fan_club**: {row['fan_club']}

## Top symbols
{top_symbols}

## Primary signals
{primary_signals}

## Missing signals
- `synthetic_no_real_avatar`
- `synthetic_no_real_stickers`
- `not_real_streamer_profile`

## Characterization
{characterization}

## Creative controls
- **creative_mode**: {row['mode']}
- **wildness_score**: {row['score']}
- **wildness_axes**: {axes}

## Media
- avatar: `(none)`
- stickers: `(none)`
"""


def render_index(rows: list[dict[str, object]]) -> str:
    lines = [
        "# Synthetic Image2 Reference Streamers",
        "",
        "This folder is generated synthetic source data for image2 reference-library batch tests.",
        "It is intentionally separate from real streamers/ data and contains English-only source text.",
        "",
        "| # | anchor_id | synthetic profile | fan_club | family | variant |",
        "|---:|---|---|---|---|---|",
    ]
    for row in rows:
        name = str(row["host_name"])
        variant = name.split()[-1]
        base_name = " ".join(name.split()[:-1])
        lines.append(
            f"| {row['row_id']} | {row['anchor_id']} | {base_name} | {row['fan_club']} | {row['family']} | {variant} |"
        )
    lines.append("")
    return "\n".join(lines)


def slugify(value: str) -> str:
    value = value.strip().replace("&", "and")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    value = value.strip("_")
    return value[:80] or "synthetic"


def dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        out.append(value)
        seen.add(key)
    return out


if __name__ == "__main__":
    main()
