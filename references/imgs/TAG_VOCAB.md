# Reference Tag Vocabulary

Reference tags are router-facing labels. `ReferenceRouter` uses exact string
matches only, so every entry should include both precise subject tags and broad
bridge tags.

Before scoring, host signals and manifest tags are normalized through
`tag_aliases.yaml`. Keep this vocabulary canonical; put common variants and
parent expansions in `tag_aliases.yaml` instead of repeating them in every
manifest entry.

## Shape

Use 2-4 broad bridge tags when relevant:

`animal`, `bird`, `food`, `fruit`, `dessert`, `sport`, `sport_ball`, `flower`,
`fantasy`, `object_body`, `mascot`, `badge`, `police_badge`, `heart`, `wing`,
`crescent`, `star`, `hat`, `crown`, `ghost`, `vehicle`, `soft_body`,
`long_object_body`, `side_swept`, `symmetric`, `non_round`

Then add precise subject tags:

`elephant`, `dragon`, `basketball`, `tennis_ball`, `sunflower`, `bee`,
`fire`, `pilot`, etc.

## Color

Prefer common color families plus important named anchors:

`red`, `orange`, `yellow`, `green`, `blue`, `purple`, `pink`, `black`, `white`,
`cream`, `gold`, `silver`, `lavender`, `mint`, `navy_blue`, `pearl_white`,
`warm_yellow`, `electric_blue`, `sky_blue`, `brown`

Specific color names are allowed when they are visually important:

`tennis_yellow`, `cherry_red`, `wine_red`, `bubblegum_pink`, `emerald`,
`honey_amber`, `moon_silver`

## Material

Use canonical material tags first:

`soft_vinyl`, `plush_fabric`, `velvet_flock`, `knitted_textile`,
`jelly_resin`, `translucent_resin`, `pearlescent_resin`,
`pearlescent_lacquer`, `matte_enamel`, `soft_enamel`, `silicone`,
`squishy_foam`, `matte_rubber`, `soft_emissive_panel`, `crystal_core`,
`glossy_resin`, `metallic_trim`, `brushed_metal_trim`, `wood`,
`embroidery`

More specific materials can follow when useful:

`frosting_resin`, `frosted_resin`, `cut_crystal`, `smoked_resin`,
`felt_fabric`, `ribbon_textile`, `clear_lens`

## Vibe

Use a few stable mood tags:

`cute`, `soft`, `playful`, `dreamy`, `sweet`, `healing`, `sporty`, `warm`,
`energetic`, `fantasy`, `dramatic`, `mysterious`, `elegant`, `retro`,
`dark_sweet`, `bold`, `gentle`, `friendly`, `idol_support`

`idol_support` is nearly universal and should not be the only meaningful vibe
match.

## Text

Use script + length + rendering tags:

`latin`, `non_latin`, `chinese`, `korean`, `arabic`, `japanese`, `short`,
`long`, `high_contrast`, `embedded_wordmark`, `embedded_in_core`,
`embroidered_text`, `script_wordmark`, `rounded_wordmark`, `athletic_logo`,
`candy_emboss`, `plush_soft`, `3d_glow`

Do not rely on `latin`, `short`, or `long` alone; those are weak matching tags.
