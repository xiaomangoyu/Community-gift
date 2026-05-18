from __future__ import annotations

import unicodedata

from .models import GiftDesign, HostInput


REFERENCE_NEGATIVE_PROMPT = (
    "human face, portrait, person, flat poster, flat sticker, only a logo, cropped handle, "
    "missing handle, incomplete product, multiple products in one image, busy background, "
    "white background, gray background, product catalog background, ecommerce cutout, white product card, white rounded rectangle panel, split-screen product sheet, detail inset panels, floor plane, contact shadow, close-up, macro shot, zoomed-in head, giant head closeup, extreme diagonal crop, bottom edge contact, pedestal, display stand, trophy base, "
    "detached accessory, separate crown, separate prop, second object, weapon-like, industrial tool, mecha fragments, too many spikes, "
    "thin skeletal handle, generic rod handle, pure black product body, black handle, glossy black resin as main material, detached head, hollow center, empty center, flat printed logo face, badge only, UI icon, "
    "militaristic brushed steel dominance, excessive chrome, low quality, blurry, unreadable central text, malformed typography, "
    "misspelled name, garbled letters, fake signature, extra text, random caption, distorted typography, broken text, "
    "handle text, handle lettering, letters on handle, vertical handle text, diagonal handle text, tilted name, curved name, "
    "blank central nameplate, empty nameplate, blank central core"
)


REFERENCE_CAMERA_CONTRACT = (
    "Generate exactly ONE premium collectible lightstick product, not a collage, not a sheet, not a poster. "
    "Full object visible from the heart-shaped lamp head through connector, slim handle, and bottom cap. "
    "Pure black background. Centered front-facing to slight 3/4 studio product render, mostly vertical upright, with less than 10 degrees of diagonal tilt. "
    "Do not twist the head so far that the central emblem becomes hard to read. NOT a close-up, NOT a macro shot. "
    "Use a strict 1:1 square composition. The complete lightstick should occupy about 55-70% of the square canvas height "
    "with at least 10% clean black margin around the top ornament, side decorations, handle, and bottom cap. "
    "The full silhouette must be visible at a glance, with obvious black negative space below the bottom cap. "
    "If the product would touch an edge, make the entire product smaller instead of cropping it. "
    "No part of the handle, bottom cap, lamp head, ribbons, or ornaments may touch or be cropped by the image edge. "
    "The bottom cap must be unobstructed and clearly visible. The bottom ending should be a small finished cap "
    "or compact charm node, not a large pedestal, not a wide decorative base, and not wider than the main lamp head."
)


REFERENCE_MATERIAL_CONTRACT = (
    "Strong reference-image material quality: smooth glossy resin, polished enamel, translucent jelly crystal inserts, "
    "pearlescent lacquer, soft metallic trim used sparingly, real material thickness, rounded inflated volume, crisp bevels, "
    "crystal refraction, rich highlight gradients, clear main light, rim light, controlled local glow. "
    "The central core is solid, full, milky luminous, and dimensional, not hollow and not cut out. "
    "If typography is present, it must be one exact short name only, placed horizontally inside the central core or central nameplate, readable but not oversized. "
    "Do not make a flat logo, signboard, poster, badge, UI icon, weapon, or industrial tool."
)


REFERENCE_STRUCTURE_CONTRACT = (
    "Strong-row product structure: one unmistakable premium cheering wand silhouette with a dominant decorative head, "
    "a full solid center core for the name, a clean custom handle shaft with no lettering, a finished connector, and a compact bottom cap. "
    "The top silhouette must be iconic and clean at thumbnail size. Build the outer contour from 2-6 bold sculpted decorative masses "
    "such as wings, crowns, fruit clusters, floral petals, flowing ribbons, flame or wave forms, depending on the theme. "
    "Decoration must wrap around and support the main head shape, as if grown from the product perimeter, never pasted flat on the face. "
    "Use a clear volume hierarchy: large luminous core, medium perimeter ornaments, small finishing nodes near the base. "
    "Avoid many tiny spikes, brackets, shards, or mechanical fragments."
)


def build_reference_seedance_prompt(
    design: GiftDesign,
    host_input: HostInput | None = None,
) -> str:
    """Build a plan-driven Seedance prompt for the Strong lightstick target."""

    plan = design.prompt_plan
    concept = design.design_concept
    text_plan = design.text_plan
    display_text = text_plan.exact_text or _display_text_target(
        host_input,
        design.community_name or "community",
        design.host_name or "creator",
    )
    materials = ", ".join(
        plan.material_terms[:4]
        or design.material_language[:4]
        or ["glossy resin", "polished enamel", "translucent jelly crystal"]
    )
    colors = ", ".join(plan.color_terms) or design.color_plan
    retained = ", ".join(plan.retained_elements[:3]) or _symbol_details(design, host_input)
    discarded = ", ".join(plan.banned_elements[:10])
    retry_focus = _retry_instruction(plan.retry_focus)

    if text_plan.mode == "post_overlay_text":
        text_contract = (
            f"TEXT PLAN: do NOT render any letters or pseudo-letters. Reserve one blank central luminous core/nameplate for later exact overlay text '{display_text}'. "
            "The blank nameplate must be smooth, horizontal, centered, and large enough for two-line text if needed. "
            "No text anywhere on the handle, rim, connector, bottom cap, ribbons, ornaments, or background.\n\n"
        )
        final_text_reminder = (
            "NO TEXT IN IMAGE, blank central nameplate only, no fake glyphs, no labels, no signatures."
        )
    else:
        text_contract = (
            f"TEXT PRIORITY FIRST: render exactly one readable text string: '{display_text}'. "
            "Place it horizontally inside the largest central luminous core or central inset nameplate only. "
            "No other text, no handle text, no random caption, no fake glyphs. "
            f"Preserve exact spelling '{display_text}'.\n\n"
        )
        final_text_reminder = (
            f"EXACT SINGLE CENTRAL TEXT ONLY: '{display_text}', no handle text, no extra text."
        )

    camera_contract = _sentence_join(
        plan.camera_contract
        or [
            "pure black background",
            "1:1 square studio product render",
            "one complete vertical lightstick fully visible",
        ]
    )
    product_contract = _sentence_join(
        plan.product_contract
        or [
            "dominant sculpted lamp head",
            "solid central luminous core",
            "clean unlettered handle",
            "compact bottom cap",
        ]
    )
    complexity = (
        "Use exactly 1 primary symbol and at most 1 supporting motif; keep large clean forms."
        if concept.complexity_level == "low"
        else "Use 2-4 bold sculpted product elements, no micro-detail collage."
    )
    black_theme_note = (
        "If a theme word says black or 黑, treat it as theme semantics only: express it with graphite gray, smoky translucent resin, silver rim highlights, or dark pearl gray, not pure black fill. "
        if "black" in retained.lower() or "黑" in retained or "black" in concept.main_proposition.lower() or "黑" in concept.main_proposition
        else ""
    )

    extraction_contract = (
        "CUTOUT-FRIENDLY PRODUCT COLOR CONTRACT: the background may be pure black, but the physical lightstick body, shell, handle, rim, and outer ornaments must NOT be pure black. "
        "Use smoked graphite gray, warm gunmetal gray, pearl gray, silver gray, cream, or colored resin for large body surfaces. "
        "Black is allowed only as a tiny accent line or symbol detail, never as the dominant shell or handle material. "
        f"{black_theme_note}"
        "All outer edges must have visible gray/silver/colored rim highlights so the object can be cleanly separated from the black background.\n\n"
    )

    return (
        text_contract
        + extraction_contract
        + f"CAMERA CONTRACT: {camera_contract}. The full product occupies 55-70% of canvas height with clean black margin below the bottom cap. Nothing touches or is cropped by the edge. Mostly upright, less than 10 degrees tilt, not close-up, not macro.\n\n"
        + f"PRODUCT CONTRACT: {product_contract}. It must read instantly as one premium collectible idol lightstick, not a badge, poster, sign, flashlight, wand prop, pedestal, or tool.\n\n"
        + f"MAIN DESIGN CONCEPT: {concept.main_proposition or design.composition} "
        + f"Primary silhouette: {concept.silhouette or 'bold sculpted lamp-head silhouette'}. "
        + f"Retain only these personalized elements: {retained}. {complexity} "
        + "Turn symbols into perimeter masses, molded resin inlays, embossed bevels, rim ornaments, or a solid luminous core; never paste emoji or flat logos on the face.\n\n"
        + f"COLORS AND MATERIALS: {colors}. {materials}, smooth rounded toy-merch volume, polished enamel, translucent jelly crystal, pearlescent lacquer, restrained metallic trim, milky luminous core, visible material thickness, crisp bevels, crystal refraction, rim light, controlled local glow. Large surfaces must stay visibly lighter than the black background.\n\n"
        + f"DISCARD / AVOID: {discarded}. No detached props, no extra mascot stickers, no secondary slogans, no hand lettering, no full animal figurine unless it is the single primary silhouette, no busy background, no white card behind the product, no split-screen layout, no detail panels.\n\n"
        + retry_focus
        + f"FINAL HARD RULES: PURE BLACK BACKGROUND ONLY, NO WHITE PRODUCT CARD, NO SPLIT PANELS, 1:1 SQUARE IMAGE, ONE FULL-BODY LIGHTSTICK, FULL HANDLE AND COMPACT BOTTOM CAP VISIBLE, NON-BLACK GRAY/SILVER/COLORED PRODUCT BODY, CENTRAL SOLID CORE/NAMEPLATE, CLEAN UNLETTERED HANDLE, {final_text_reminder}"
    )


def build_reference_negative_prompt(design: GiftDesign | None = None) -> str:
    if not design:
        return REFERENCE_NEGATIVE_PROMPT
    base_prompt = REFERENCE_NEGATIVE_PROMPT
    if design.text_plan.mode == "post_overlay_text":
        for term in [
            "blank central nameplate, ",
            "empty nameplate, ",
            "blank central core",
        ]:
            base_prompt = base_prompt.replace(term, "")
    planned_bans = design.prompt_plan.banned_elements if design.prompt_plan else []
    extras = ", ".join([*planned_bans[:12], *design.negative_constraints[:8]])
    if not extras:
        return base_prompt
    return f"{base_prompt}, {extras}"


def _sentence_join(values: list[str]) -> str:
    return "; ".join(value.strip().rstrip(".") for value in values if value.strip())


def _retry_instruction(failures: list[str]) -> str:
    if not failures:
        return ""
    instructions = {
        "cropping_fail": "Retry correction: zoom out, keep 10% black margin around the entire product and visible black space below the bottom cap.",
        "text_fail": "Retry correction: prioritize a smooth blank central nameplate or exact central text only; remove every other glyph-like mark.",
        "complexity_fail": "Retry correction: remove extra ornaments and keep only one primary symbol plus one supporting motif.",
        "concept_fail": "Retry correction: make the primary symbol shape the lamp-head silhouette instead of appearing as a sticker or detached prop.",
        "product_form_fail": "Retry correction: return to a clear vertical lightstick skeleton with lamp head, connector, handle, and bottom cap.",
        "material_fail": "Retry correction: reduce neon spill and flat graphics; emphasize glossy resin, enamel, jelly crystal, and real thickness.",
    }
    selected = [instructions[failure] for failure in failures if failure in instructions]
    if not selected:
        return ""
    return " ".join(selected[:3]) + "\n\n"


def _symbol_details(design: GiftDesign, host: HostInput | None = None) -> str:
    if host and host.symbols:
        return ", ".join(host.symbols[:3])

    blocked = [
        "lightstick",
        "full-body",
        "text",
        "typography",
        "core",
        "heart-frame",
        "background",
    ]
    symbols = [
        item
        for item in design.required_elements
        if item not in {design.community_name, design.host_name}
        and not (
            host
            and item in {host.primary_text, host.secondary_text, host.community_name, host.host_name}
        )
        and item not in design.color_plan
        and not any(word in item.lower() for word in blocked)
    ]
    return ", ".join(symbols[:3]) if symbols else "small heart accents, subtle rim charms"


def _display_text_target(
    host_input: HostInput | None,
    community: str,
    host_name: str,
) -> str:
    if host_input and host_input.host_name:
        cleaned = _clean_exact_text(host_input.host_name)
        if cleaned:
            return cleaned
    return community if community and community != "Community" else host_name


def _clean_exact_text(value: str) -> str:
    allowed_punctuation = {" ", "-", "_", ".", "'", "&"}
    chars: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or char in allowed_punctuation:
            chars.append(char)
    return " ".join("".join(chars).split())
