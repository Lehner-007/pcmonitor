"""Read-only firmware source with explicit units and exact slot association."""
import os
import re
import shutil
import subprocess
from datetime import datetime

UNKNOWN='@unknown'


def parse_memory_devices(text):
    devices={}
    for block in re.split(r'\n(?=Handle )',text):
        pairs=re.findall(r'^\s*([^:\n]+):\s*(.*?)\s*$',block,re.M)
        values={};conflicts=set()
        for key,value in pairs:
            if key in values and values[key]!=value:conflicts.add(key)
            values[key]=value
        locator=values.get('Locator')
        if not locator:continue
        fields={}
        for target,keys in [('ram_configured_rate',('Configured Memory Speed','Configured Clock Speed')),('ram_reported_speed',('Speed',))]:
            present=[values[k] for k in keys if k in values]
            value=present[0] if present else ''
            match=re.fullmatch(r'(\d+)\s+(MT/s|MHz)',value)
            invalid=any(k in conflicts for k in keys) or len(set(present))>1
            fields[target]=f'{int(match[1])} {match[2]}' if match and 1<=int(match[1])<=20000 and not invalid else UNKNOWN
        empty=values.get('Size')=='No Module Installed'
        status='ram_fw_empty' if empty else 'ram_fw_ok' if all(v!=UNKNOWN for v in fields.values()) else 'ram_fw_incomplete'
        if 'Locator' in conflicts or locator in devices:
            devices[locator]=dict(status='ram_fw_conflict',fields={key:UNKNOWN for key in fields})
        else:devices[locator]=dict(status=status,fields=fields)
    return devices


def query_memory_firmware(elevated=False, source=None, admin_status=None):
    """Use bundled helper output when elevated; never request elevation here."""
    captured=datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %Z')
    base=dict(captured_at=captured,devices={},warning='',elevated=elevated)
    if elevated:
        statuses={'missing':'ram_fw_missing','timeout':'ram_fw_timeout','denied':'ram_fw_denied','cancelled':'ram_fw_denied','failed':'ram_fw_failed','unsafe':'ram_fw_failed'}
        if source is None:return {**base,'status':'ram_fw_admin_missing' if admin_status=='missing' else statuses.get(admin_status,'ram_fw_failed')}
        base['captured_at']=source['captured_at']
        if source['status']!='ok':return {**base,'status':statuses.get(source['status'],'ram_fw_failed')}
        text,stderr=source['stdout'],source.get('stderr','')
    else:
        tool=shutil.which('dmidecode')
        if not tool:return {**base,'status':'ram_fw_missing'}
        try:result=subprocess.run([tool,'--type','17'],capture_output=True,text=True,errors='replace',timeout=8,check=False,env={**os.environ,'LC_ALL':'C'})
        except subprocess.TimeoutExpired:return {**base,'status':'ram_fw_timeout'}
        except OSError:return {**base,'status':'ram_fw_failed'}
        if result.returncode:return {**base,'status':'ram_fw_failed'}
        base['captured_at']=datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %Z')
        text,stderr=result.stdout,result.stderr
    normalized=re.sub(r'\s+',' ',(text+'\n'+stderr).replace('#',''))
    warning='@ram_fw_smbios_warning' if re.search(r'SMBIOS.{0,250}not fully supported|not fully supported.{0,250}SMBIOS',normalized,re.I) else ''
    if warning:
        versions=re.findall(r'(?:dmidecode|SMBIOS) \d+(?:\.\d+)+',text)
        if versions:warning+=' ('+'; '.join(dict.fromkeys(versions))+')'
    devices=parse_memory_devices(text)
    status='ram_fw_ok' if devices and all(record['status'] in ('ram_fw_ok','ram_fw_empty') for record in devices.values()) else 'ram_fw_incomplete'
    return {**base,'status':status,'devices':devices,'warning':warning}


def module_firmware(source,slot):
    record=source['devices'].get(slot)
    status=record['status'] if record else source['status'] if source['status']!='ram_fw_ok' else 'ram_fw_unmatched'
    if status=='ram_fw_empty':status='ram_fw_conflict'  # lshw says occupied, DMI says empty
    fields=record['fields'].copy() if record else dict(ram_configured_rate=UNKNOWN,ram_reported_speed=UNKNOWN)
    fields.update(ram_firmware_mode='@ram_fw_mode_admin' if source.get('elevated') else '@ram_fw_mode_normal',ram_firmware_source='dmidecode --type 17',ram_firmware_time=source['captured_at'],ram_firmware_status='@'+status,ram_firmware_warning=source['warning'] or '@ram_fw_no_warning')
    return dict(status=status,captured_at=source['captured_at'],fields=fields)


def sync_ram_row(record,detail):
    fields=detail.get('fields',{})
    base=' · '.join(fields.get(key,UNKNOWN) for key in ('manufacturer','model','module_capacity'))
    record['ram_base_value']=base
    fw=detail.get('firmware',{})
    rate=fw.get('fields',{}).get('ram_configured_rate',UNKNOWN)
    valid=fw.get('status') in ('ram_fw_ok','ram_fw_incomplete','ram_fw_old') and rate!=UNKNOWN
    record['value']=base+' · @ram_configured_rate: '+(rate+' (@ram_firmware_short)' if valid else UNKNOWN)
    if fw.get('status')=='ram_fw_old':
        record['value']+=' · @ram_fw_old · '+fw.get('captured_at','')
    elif not valid and fw:
        record['value']+=' · @'+fw['status']
