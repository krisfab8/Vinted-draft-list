"""Short writing contract; deterministic post-processing remains authoritative."""
import json
from app.config import PROMPTS_DIR


def price_guidance():
    """Keep all existing bands; omit examples and unrelated listing schedules."""
    source = (PROMPTS_DIR / 'pricing_rules.md').read_text()
    bands = '\n'.join(' '.join(line.split()) for line in source.splitlines()
                      if line.startswith('|') and '£' in line)
    luxury = source.split('## Luxury Brand List', 1)[1].split('## Seasonal Adjustment', 1)[0]
    return ('Unverified Vinted UK asking-price guidance, aiming at roughly one month. '
            'Standard/average condition: lower 40%; good brand/condition: midpoint; '
            'luxury in very good condition: upper 25–30%; exceptional: ceiling. '
            'Buy price, when supplied, is a 3x minimum floor, not the main driver. '
            'Out of season: -15%; peak season: ceiling. Women use equivalent bands.\n'
            + bands + '\nLuxury brands:\n' + luxury.strip())


def build_prompt(item, hints, categories):
    from app.services.copy_quality import writer_evidence
    item = writer_evidence(item)
    fields = ('brand', 'item_type', 'sub_brand', 'model_name', 'tagged_size', 'normalized_size',
              'trouser_waist', 'trouser_length', 'materials', 'material_confidence', 'colour',
              'colour_secondary', 'pattern', 'cut', 'style', 'gender', 'made_in', 'fabric_mill',
              'fabric_line', 'material_hint', 'tag_keywords', 'tag_keywords_confidence',
              'garment_text', 'condition_summary', 'flaws_note', 'buy_price_gbp', 'low_confidence_fields')
    data = {k:item[k] for k in fields if item.get(k) is not None}
    if hints:
        data['seller_confirmed'] = hints
    return f'''Write one valid listing JSON object using only the supplied evidence. No markdown.
Seller-confirmed hints override extracted data. Missing facts stay null; never invent labels,
materials, origin, damage, model names or ruler measurements. Keep tagged and normalized size.
No chest-size inference from ruler readings. Measurements are handled separately by the app.
Title: brand, relevant model/sub-brand, colour, gender, UK size, premium cloth/fibre, item type; aim <=70 characters.
Shoes: Brand + Model + Colour + Type + UK Size. No W/L for shoes.
Trousers: preserve visible W/L; activewear keeps letter size, optional W suffix.
Tailoring: preserve tagged EU/UK evidence; the app handles conversion. Do not convert twice.
Use specific garment type: collared short-placket polo is a polo, not a jumper.
Retain fabric mill/line and clearly read tag keywords. Include all high-confidence garment_text verbatim in the description as logo/print details, even unfamiliar names. Never turn club/company text into the maker or claim affiliation. Do not put uncertain keywords in title.
Rank premium natural fibres first; keep every distinct composition entry, including lining.
Description: one short opening, then dash bullets in order: Size, Made in, Fabric mill,
Fabric line, Fit, Model, Material. Omit unknown facts. Keep UK and EU/tagged sizes together
on the first Size line where supported, e.g. '- Size: UK 44R / EU 54 (label)'.
Do not put condition or flaws in description: the app adds one condition line.
Keep visible flaws in flaws_note and condition_summary. Never infer storage/history.
Preserve the supplied condition grade; never improve it. Include known size and exact
material percentages. Avoid generic performance/lightweight claims unless a tag states them.
Exclude low-confidence pattern, secondary colour, model and tag claims from buyer-facing copy; no unsupported designer/rare claims. Finish with relevant Keywords sentence.
Use plain natural English and useful buyer details; no hype, repetitive tags or invented facts.
Return ONLY these six fields: title (string <=120 chars), description (string),
price_gbp (nonnegative number), category (string), style (string or null), premium (boolean).
All label facts, sizes, condition and confidence are retained by the app; do not echo them.
Never invent a missing size or put TBC in the title. Missing colour stays absent from copy.
Premium cloth is a fabric supplier, not the garment brand. Include confirmed premium fibre,
mill (as cloth) and construction in the title ahead of optional colour/gender/fit.
The price is an unverified asking suggestion, not a researched sale value.
Use this permitted category mapping:
{categories}
Price guidance (reference only; never claim a live market lookup):
{price_guidance()}
Evidence:
{json.dumps(data, ensure_ascii=False, separators=(',', ':'))}
'''
