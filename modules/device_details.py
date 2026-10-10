"""Device identities and read-only detail data; independent of GTK."""
import hashlib
import json
import math
from pathlib import Path
from .hardware_sources import valid_edid

UNKNOWN='@unknown'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()


def eligible(record):
    return record.get('occupancy')=='occupied' and bool(record.get('device_id'))


def bank_identity(bank):
    return fingerprint({key:bank.get(key) for key in ('id','slot','vendor','product','serial','size')})


def edid_fields(edid):
    values=dict(manufacturer=UNKNOWN,model=UNKNOWN,serial=UNKNOWN,dimensions=UNKNOWN,diagonal=UNKNOWN)
    if not valid_edid(edid):return values
    vendor=int.from_bytes(edid[8:10],'big')
    letters=[(vendor>>shift)&31 for shift in (10,5,0)]
    if all(1<=n<=26 for n in letters):values['manufacturer']=''.join(chr(64+n) for n in letters)
    for offset in (54,72,90,108):
        descriptor=edid[offset:offset+18]
        if descriptor[:5] in (b'\0\0\0\xfc\0',b'\0\0\0\xff\0'):
            text=descriptor[5:18].decode('ascii','replace').strip('\n \0')
            if text:values['model' if descriptor[3]==0xfc else 'serial']=text
    serial=int.from_bytes(edid[12:16],'little')
    if values['serial']==UNKNOWN and serial:values['serial']=str(serial)
    width,height=edid[21],edid[22]
    # Zero denotes undefined dimensions/aspect-ratio encoding, not centimetres.
    if width and height:
        values['dimensions']=f'@approx {width} × {height} cm'
        values['diagonal']=f'@approx {math.hypot(width,height)/2.54:.1f} @inches'
    return values


def edid_modes(edid):
    """Base EDID detailed timings only; this is explicitly not a full mode list."""
    if not valid_edid(edid):return []
    modes=[]
    for offset in (54,72,90,108):
        d=edid[offset:offset+18];clock=int.from_bytes(d[:2],'little')*10000
        if not clock:continue
        width=d[2]+((d[4]>>4)<<8);hblank=d[3]+((d[4]&15)<<8)
        height=d[5]+((d[7]>>4)<<8);vblank=d[6]+((d[7]&15)<<8)
        # Interlaced descriptors need field/frame interpretation; do not guess.
        if not width or not height or d[17]&128:continue
        rate=clock/((width+hblank)*(height+vblank))
        if 1<=rate<=1000:
            mode=f'{width}x{height} / {rate:.2f} Hz'
            if mode not in modes:modes.append(mode)
    return modes


def monitor_detail(connector, output, gpu_name=''):
    fields=edid_fields(connector['edid'])
    modes='\n'.join(output.get('modes',[])) if output else ''
    if not modes:
        fallback=edid_modes(connector['edid'])
        modes='@edid_modes_partial\n'+'\n'.join(fallback) if fallback else UNKNOWN
    fields.update(drm_connector=connector['name'],graphics_card=connector['gpu']+(' · '+gpu_name if gpu_name else ''),
                  xrandr_mapping=output['name'] if output else '@mapping_unknown',
                  active_mode=output['mode'] if output else UNKNOWN,
                  supported_modes=modes)
    identity='display:'+connector['name']+':'+hashlib.sha256(connector['edid']).hexdigest()
    return dict(id=identity,family='display',name=fields['model'] if fields['model']!=UNKNOWN else connector['name'],
                connector=connector['name'],path=str(connector['path']),edid=connector['edid'],fields=fields)


def current_state(detail):
    """True=verified same occupied device; False=removed/replaced; None=unverifiable."""
    from .inventory import read,run,walk
    if detail['family']=='display':
        path=Path(detail['path'])
        if not path.exists():return False
        status=read(path/'status')
        if not status:return None
        if status!='connected':return False
        try:edid=(path/'edid').read_bytes()
        except OSError:return None
        return edid==detail['edid']
    if detail['family']=='ram':
        return None  # RAM is a captured state, never live-polled or re-queried here.
    if detail['family']=='pci':
        for item in detail['devices']:
            path=Path(item['path'])
            if not path.exists():return False
            if read(path/'vendor')!=item['vendor'] or read(path/'device')!=item['device']:return False
        return bool(detail['devices'])
    return None
