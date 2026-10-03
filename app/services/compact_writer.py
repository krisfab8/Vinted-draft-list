"""Short writing contract; deterministic post-processing remains authoritative."""
import json
from app.config import PROMPTS_DIR, SCHEMA_PATH


def build_prompt(item, hints, categories):
    from app.services.copy_quality import writer_evidence
    item = writer_evidence(item)
    data = {k:v for k,v in item.items() if not k.startswith('_') and k != 'measurement_proposals'}
    if hints:
        data['seller_confirmed'] = hints
    return f'''Write one valid listing JSON object using only the supplied evidence. No markdown.
Seller-confirmed hints override extracted data. Missing facts stay null; never invent labels,
materials, origin, damage, model names or ruler measurements. Keep tagged and normalized size.
No chest-size inference from ruler readings. Measurements are handled separately by the app.
Title: brand, relevant model/sub-brand, item type, gender, size, colour; aim <=70 characters.
Shoes: Brand + Model + Colour + Type + UK Size. No W/L for shoes.
Trousers: preserve visible W/L; activewear keeps letter size, optional W suffix.
Tailoring: preserve tagged EU/UK evidence; the app handles conversion. Do not convert twice.
Use specific garment type: collared short-placket polo is a polo, not a jumper.
Retain fabric mill/line and clearly read tag keywords. Do not put uncertain keywords in title.
Rank premium natural fibres first; keep every distinct composition entry, including lining.
Description: concise opening and size/material/origin/model bullets where known.
Do not put condition or flaws in description: the app adds one condition line.
Keep visible flaws in flaws_note and condition_summary. Never infer storage/history.
Exclude low-confidence pattern, secondary colour, model and tag claims from buyer-facing copy; no unsupported designer/rare claims. Finish with relevant Keywords sentence.
Use plain natural English and useful buyer details; no hype, repetitive tags or invented facts.
Return brand, item_type, title, description, tagged_size, normalized_size, materials, colour,
gender, price_gbp, category, condition_summary, flaws_note, made_in, fabric_mill, fabric_line,
material_hint, style, cut, pattern, model_name, tag_keywords, tag_keywords_confidence,
brand_confidence, material_confidence, confidence, low_confidence_fields, premium.
Preserve supplied trouser_waist/trouser_length where relevant. price_gbp must be a nonnegative
number: a tentative asking price, not a claim of a researched sale value.
Preserve supplied buy_price_gbp; omit it when unknown. confidence must be a number from 0 to 1
or omitted when unknown. Never return null for numeric fields.
brand_confidence, material_confidence, tag_keywords_confidence must be string labels
"high", "medium" or "low", copied from extraction; they are never numeric scores.
Omit unknown optional fields whose schema does not allow null. Required fields must follow
this exact output schema (including lowercase gender values):
{json.dumps(json.loads(SCHEMA_PATH.read_text()), separators=(',', ':'))}
Use this permitted category mapping:
{categories}
Price guidance (reference only; never claim a live market lookup):
{(PROMPTS_DIR / 'pricing_rules.md').read_text()}
Evidence:
{json.dumps(data, ensure_ascii=False, separators=(',', ':'))}
'''
