"""Optional ruler proposals; confirmed dimensions never replace garment tag size."""
import json
import math
import re
from pathlib import Path
from app.services import model_usage

ROLES = {'measure_pit_to_pit':'Pit-to-pit (flat width)',
         'measure_length':'Back length', 'measure_sleeve':'Sleeve length'}
PHOTO_ROLES = ('front','brand','model_size','material','back','extra', *ROLES)


def parse_roles(raw, count):
    if not raw:
        return None
    roles=json.loads(raw)
    if not isinstance(roles,list) or len(roles)!=count or count>20:
        raise ValueError('Choose one role for each photo (maximum 20).')
    if "front" not in roles:
        raise ValueError("Choose a Front photo.")
    seen=set()
    for role in roles:
        if not isinstance(role,str) or role not in PHOTO_ROLES:
            raise ValueError('Unknown photo role.')
        if role!='extra' and role in seen:
            raise ValueError('Use one photo per named role; choose Extra for others.')
        seen.add(role)
    return roles


def role_map(paths, roles):
    result={}; extra=0
    for path,role in zip(paths,roles):
        if role=='extra':
            extra+=1; role=f'extra_{extra:02d}'
        result[role]=path
    return result


def number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def proposal(raw, role, source):
    result={'role':role,'source_photo':source,'value_cm':None,'status':'unknown',
            'reason':'Both ruler references and the garment edge must be clear.'}
    if not isinstance(raw,dict): return result
    if raw.get('start_visible') is not True or raw.get('end_visible') is not True or raw.get('aligned') is not True:
        return result
    if raw.get('confidence') != 'high' or raw.get('unit') not in ('cm','in'):
        return result
    start,end=raw.get('start'),raw.get('end')
    if not number(start) or not number(end) or start<0 or end<=start: return result
    value=(end-start)*(2.54 if raw['unit']=='in' else 1)
    if not .5<=value<=250: return result
    result.update(value_cm=round(value*2)/2,status='needs_confirmation',
                  start=start,end=end,unit=raw['unit'],
                  reason='Approximate ruler reading; confirm the measurement and reference points.')
    return result


def analyze(folder, provider):
    from app import extractor
    from app.config import ANTHROPIC_API_KEY, HAIKU_MODEL, OPENAI_VISION_MODEL
    import anthropic
    photos=[]; sources=[]
    for role in ROLES:
        path=next((Path(folder)/f'{role}{ext}' for ext in ('.jpg','.jpeg','.png','.webp')
                   if (Path(folder)/f'{role}{ext}').exists()),None)
        if path:
            data,media_type=extractor._compress_image(path,1568)
            photos.append({'type':'image','source':{'type':'base64','data':data,'media_type':media_type}})
            sources.append((role,path.name))
    if not photos: return []
    prompt='''Read only explicitly photographed garment measurements. Never infer zero from a cropped ruler.
A readable number alone is not a full length. Both start reference and end garment edge must be visible,
the ruler straight and aligned with that dimension. Do not infer chest circumference or tagged size.
Distinguish cm and inches. If anything is unclear, return null start/end and low confidence.
Image order is listed below. Return JSON {"readings":[{"source_photo":"exact filename",
"start":number or null,"end":number or null,"unit":"cm" or "in" or null,
"start_visible":boolean,"end_visible":boolean,"aligned":boolean,"confidence":"high" or "low"}]}.
'''+json.dumps([{'role':ROLES[r],'source_photo':s} for r,s in sources])
    try:
        if provider=='claude-haiku':
            client=anthropic.Anthropic(api_key=ANTHROPIC_API_KEY,max_retries=0,timeout=30)
            response=model_usage.call(client.messages.create,stage='measurements',model=HAIKU_MODEL,
                max_tokens=600,messages=[{'role':'user','content':photos+[{'type':'text','text':prompt}]}])
        elif provider=='openai':
            from app.services.openai_provider import generate
            response=generate(prompt,OPENAI_VISION_MODEL,600,images=photos,stage="measurements")
        else:
            return [proposal(None,r,s) for r,s in sources]
        readings=extractor._safe_json_loads(response.content[0].text).get('readings',[])
        if not isinstance(readings,list): readings=[]
        by_source={r.get('source_photo'):r for r in readings if isinstance(r,dict) and isinstance(r.get('source_photo'),str)}
        return [proposal(by_source.get(s) if sum(isinstance(v,dict) and v.get("source_photo")==s for v in readings)==1 else None,r,s) for r,s in sources]
    except Exception:
        # Call failures were recorded without secrets; the garment listing still works.
        return [proposal(None,r,s) for r,s in sources]


def confirmed(values):
    if not isinstance(values,list) or len(values)>3: raise ValueError('Provide up to three measurements.')
    result=[]; seen=set()
    for value in values:
        if not isinstance(value,dict): raise ValueError('Invalid measurement.')
        role=value.get('role'); cm=value.get('value_cm')
        if not isinstance(role,str) or role not in ROLES or role in seen or not number(cm) or not .5<=cm<=250:
            raise ValueError('Measurements must have unique roles and values between 0.5 and 250 cm.')
        seen.add(role)
        result.append({'role':role,'value_cm':round(cm,1),'confirmed':True})
    return result


def apply_description(listing):
    description=listing.get('description','')
    description=re.sub(r'\n*Measurements \(seller confirmed\):\n(?:- [^\n]*\n?)+\n*','\n\n',description)
    values=listing.get('measurements',[])
    if values:
        block='Measurements (seller confirmed):\n'+'\n'.join(
            f"- {ROLES[v['role']]}: approx. {v['value_cm']:g} cm" for v in values)
        parts=description.split('Keywords:',1)
        description=parts[0].rstrip()+'\n\n'+block+('\n\nKeywords:'+parts[1] if len(parts)>1 else '')
    listing['description']=description.strip()
    return listing
