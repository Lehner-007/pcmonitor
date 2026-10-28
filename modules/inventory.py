"""Read-only Linux inventory. Optional, explicitly requested pkexec lshw query."""
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from .hardware_sources import (cpu_set,pci_address,slot_matches,nvidia_memory,dmidecode_speeds,ram_speed,xrandr_outputs,match_monitor,bluez_devices,sensor_origin,sensor_identity,lan_states,lan_diagnostics,redact,wifi_metrics,slot_occupants)

from .device_details import monitor_detail,bank_identity,fingerprint
from .admin_probe import query_admin_sources
from .ram_firmware import query_memory_firmware,module_firmware,sync_ram_row
from .processes import run_capped

SECTIONS = ('board','cpu','ram','gpu','display','usb','disk','lan','wifi','bluetooth','audio','reader','pci','sensors','system','events')
UNKNOWN = '@unknown'
MAX_SESSION_EVENTS = 1000


def retain_events(events,new,limit=MAX_SESSION_EVENTS):
    omitted=max(0,len(events)+len(new)-limit)
    events.extend(new)
    return omitted


def read(path):
    try:
        return Path(path).read_text(errors='replace').strip()
    except OSError:
        return ''


def run(args, diagnostics=None, timeout=8, allowed_exits=(), cancel_event=None):
    if not shutil.which(args[0]):
        if diagnostics is not None: diagnostics.append((args[0], 'missing'))
        return ''
    status, returncode, stdout, _stderr = run_capped(
        args, timeout=timeout, cancel_event=cancel_event,
        env={**os.environ, 'LC_ALL': 'C'})
    if status == 'cancelled':
        from .jobs import Cancelled
        raise Cancelled()
    if status != 'ok' and not (status == 'failed' and (returncode, stdout.strip()) in allowed_exits):
        if diagnostics is not None:
            diagnostics.append((args[0], status))
        return ''
    if returncode and (returncode, stdout.strip()) not in allowed_exits:
        if diagnostics is not None: diagnostics.append((args[0], 'failed'))
        return ''
    return stdout


def json_command(args, diagnostics, cancel_event=None):
    try: return json.loads(run(args, diagnostics, cancel_event=cancel_event))
    except (ValueError, TypeError): return {}


def quantity(value):
    try:
        value = int(value)
        for unit in ('B','KiB','MiB','GiB','TiB'):
            if value < 1024 or unit == 'TiB': return f'{value:.2f} {unit}'
            value /= 1024
    except (ValueError, TypeError): return UNKNOWN


def rotation_label(value):
    if type(value) is bool:return 'HDD' if value else '@nonrotating'
    if type(value) is int and value in (0,1):return 'HDD' if value==1 else '@nonrotating'
    return UNKNOWN


def row(name, value='', occupancy='', personal=False, kind='property'):
    return dict(name=name, value=str(value) if value not in ('',None) or occupancy=='empty' else UNKNOWN, occupancy=occupancy, personal=personal,kind=kind)


def walk(tree):
    if isinstance(tree, dict):
        yield tree
        for child in tree.get('children', []): yield from walk(child)
    elif isinstance(tree, list):
        for child in tree: yield from walk(child)


def inventory(cancel_event=None):
    data = {s: [] for s in SECTIONS}
    diagnostics = []
    details_by_id={}
    captured=datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %Z')
    query_mode='ram_mode_normal'
    def checkpoint():
        if cancel_event and cancel_event.is_set():
            from .jobs import Cancelled
            raise Cancelled()
    checkpoint()
    def add(section, name, value='', occupancy='', personal=False, kind='property'):
        item=row(name,value,occupancy,personal,kind)
        data[section].append(item)
        return item
    for key,filename in [('manufacturer','board_vendor'),('model','board_name'),('bios_vendor','bios_vendor'),('bios_version','bios_version'),('bios_date','bios_date')]:
        checkpoint()
        value=read('/sys/class/dmi/id/'+filename)
        if key=='bios_date':
            try:value=datetime.strptime(value,'%m/%d/%Y').strftime('%d.%m.%Y')
            except ValueError:pass
        add('board',key,value)
    add('board','firmware', 'UEFI' if Path('/sys/firmware/efi').exists() else UNKNOWN)
    blocks = read('/proc/cpuinfo').split('\n\n')
    cpus = [dict(re.findall(r'^([^:\n]+)\s*:\s*(.*)$',b,re.M)) for b in blocks if b]
    cpus = [{k.strip():v for k,v in c.items()} for c in cpus]
    add('cpu','model',next((c.get('model name') or c.get('Processor') for c in cpus if c.get('model name') or c.get('Processor')), ''))
    threads = list(Path('/sys/devices/system/cpu').glob('cpu[0-9]*'))
    present=cpu_set(read('/sys/devices/system/cpu/present'))
    online=cpu_set(read('/sys/devices/system/cpu/online'))
    cores = {(read(c/'topology/physical_package_id'),read(c/'topology/core_id')) for c in threads if int(c.name[3:]) in online}
    add('cpu','present_cpus',len(present) if present else '')
    add('cpu','online_cpus',len(online) if online else '')
    add('cpu','cores',len(cores) if cores and all(a and b for a,b in cores) else '')
    add('cpu','threads',len(cpus) or '')
    mhz=[c['cpu MHz'] for c in cpus if 'cpu MHz' in c]
    add('cpu','clock', f'{min(map(float,mhz)):.0f}–{max(map(float,mhz)):.0f} MHz' if mhz else '')
    total=re.search(r'MemTotal:\s*(\d+)',read('/proc/meminfo'))
    add('ram','total',quantity(int(total[1])*1024) if total else '')
    elevated=os.environ.get('PCMONITOR_ADMIN_QUERY')=='1'
    admin=query_admin_sources(cancel_event) if elevated else None
    checkpoint()
    hardware={}
    lshw_source=admin.get('sources',{}).get('lshw') if admin else None
    if lshw_source and lshw_source['status']=='ok':
        try:hardware=json.loads(lshw_source['stdout'])
        except ValueError:hardware={}
    if elevated:
        query_mode='ram_mode_admin' if hardware else 'ram_mode_fallback'
        diagnostics.append(('admin_query','admin_done' if hardware else 'admin_failed'))
        add('system','admin_probe_status','@admin_probe_'+admin['status'])
        if lshw_source:add('system','admin_lshw_status','@admin_source_'+lshw_source['status'])
    if not hardware:hardware=json_command(['lshw','-json'],diagnostics,cancel_event)
    captured=lshw_source['captured_at'] if hardware and query_mode=='ram_mode_admin' else datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %Z')
    hw=list(walk(hardware))
    add('system','lshw_package',run(['dpkg-query','-W','--showformat=${Version}','lshw'],diagnostics,cancel_event=cancel_event).strip())
    checkpoint()
    firmware=query_memory_firmware(elevated=elevated,source=admin.get('sources',{}).get('dmidecode') if admin else None,admin_status=admin['status'] if admin else None,cancel_event=cancel_event)
    checkpoint()
    add('system','ram_firmware_status','@'+firmware['status'])
    if firmware['warning']:add('system','ram_firmware_warning',firmware['warning'])
    # Keep successful firmware source data visible even if lshw cannot provide banks.
    for locator,device in firmware['devices'].items():
        if device['status']=='ram_fw_empty':continue
        add('system','dmidecode / '+locator,'@ram_configured_rate: '+device['fields']['ram_configured_rate']+' · @ram_reported_speed: '+device['fields']['ram_reported_speed']+' · @'+device['status']+' · '+firmware['captured_at'])
    speeds={}
    banks=[h for h in hw if str(h.get('id','')).startswith('bank:')]
    for h in banks:
        checkpoint()
        size=h.get('size'); desc=h.get('description',''); empty='empty' in desc.lower()
        details=' · '.join(str(x) for x in [h.get('vendor') or UNKNOWN,h.get('product') or UNKNOWN,quantity(size) if size else UNKNOWN]) if not empty else ''
        item=add('ram',h.get('slot') or h.get('id'), details, 'empty' if empty else 'occupied' if size else 'unknown',kind='slot')
        item['slot_id']='ram-slot:'+fingerprint([h.get('id'),h.get('slot')])
        if item['occupancy']=='occupied':
            identity='ram:'+bank_identity(h)
            item['device_id']=identity
            details_by_id[identity]=dict(captured_at=captured,query_mode=query_mode,capture_status='ram_capture_ok',occupancy='occupied',slot_id=item['slot_id'],id=identity,family='ram',name=h.get('slot') or h['id'],bank_id=h['id'],slot=h.get('slot'),fingerprint=bank_identity(h),fields=dict(manufacturer=h.get('vendor') or UNKNOWN,model=h.get('product') or UNKNOWN,module_capacity=quantity(size),module_speed=ram_speed(h,speeds),serial=h.get('serial') or UNKNOWN))
            detail=details_by_id[identity]
            detail['firmware']=module_firmware(firmware,h.get('slot'))
            detail['fields'].update(detail['firmware']['fields'])
            sync_ram_row(item,detail)
    if not banks:
        for key in ('slots','module_manufacturer','module_model','module_capacity','module_speed'):add('ram',key,'', 'unknown')
    pci_names={}
    for block in run(['lspci','-vmm','-D'],diagnostics,cancel_event=cancel_event).split('\n\n'):
        fields=dict(re.findall(r'^(\w+):\s*(.*)$',block,re.M))
        if 'Slot' in fields: pci_names[fields['Slot']]=' · '.join(fields.get(k,'') for k in ('Vendor','Device')).strip(' ·')
    pci_devices=list(Path('/sys/bus/pci/devices').glob('*'))
    nvidia={}
    if any(read(p/'vendor')=='0x10de' and read(p/'class').startswith('0x03') for p in pci_devices):
        nvidia=nvidia_memory(run(['nvidia-smi','--query-gpu=pci.bus_id,memory.total','--format=csv,noheader,nounits'],diagnostics,cancel_event=cancel_event))
    for p in pci_devices:
        checkpoint()
        name=pci_names.get(p.name) or f'{read(p/"vendor")}:{read(p/"device")}'
        driver=(p/'driver').resolve().name if (p/'driver').exists() else UNKNOWN
        add('pci',p.name,f'{name} · {driver}',kind='component')
        if read(p/'class').startswith('0x03'):
            add('gpu',p.name,name);add('gpu',p.name+' / driver',driver)
            add('gpu',p.name+' / VRAM',quantity(read(p/'mem_info_vram_total') or nvidia.get(pci_address(p.name))))
    for slot in Path('/sys/bus/pci/slots').glob('*'):
        checkpoint()
        address=read(slot/'address'); matched=slot_occupants(address,pci_devices,read)
        item=add('pci','PCIe '+slot.name,', '.join(pci_names.get(p.name,p.name) for p in matched), 'occupied' if matched else 'unknown',kind='slot')
        if matched:
            identity='pci-slot:'+slot.name+':'+','.join(p.name for p in matched)
            item['device_id']=identity
            details_by_id[identity]=dict(id=identity,family='pci',name='PCIe '+slot.name,fields=dict(pci_address=address,model=item['value']),devices=[dict(path=str(p),vendor=read(p/'vendor'),device=read(p/'device')) for p in matched])
    connectors=[]
    for p in Path('/sys/class/drm').glob('card*-*'):
        checkpoint()
        if not (p/'status').exists():continue
        try:edid=(p/'edid').read_bytes()
        except OSError:edid=b''
        card=p.name.split('-',1)[0]
        gpu=(p.parent/card/'device').resolve().name
        connectors.append(dict(path=p,name=p.name,gpu=gpu,status=read(p/'status'),edid=edid))
    outputs=xrandr_outputs(run(['xrandr','--prop'],diagnostics,cancel_event=cancel_event))
    for connector in connectors:
        checkpoint()
        model='';edid=connector['edid']
        for offset in (54,72,90,108):
            if edid[offset:offset+5]==b'\0\0\0\xfc\0':model=edid[offset+5:offset+18].decode('ascii','replace').strip('\n \0')
        output=match_monitor(connector,connectors,outputs)
        mode=output['mode'] if output else UNKNOWN
        state=connector['status'];physical=not any(x in connector['name'] for x in ('Virtual','Writeback'))
        # DRM disconnected also covers powered-off displays; not proof of empty.
        item=add('display',connector['name']+' / '+connector['gpu'], ' · '.join([model or UNKNOWN,state,mode,'XRandR '+output['name'] if output else '@mapping_unknown', '@connector' if physical else '@virtual']), 'occupied' if state=='connected' and physical else 'unknown')
        if item['occupancy']=='occupied':
            detail=monitor_detail(connector,output,pci_names.get(connector['gpu'],''))
            item['device_id']=detail['id'];details_by_id[detail['id']]=detail
    for p in Path('/sys/bus/usb/devices').glob('*'):
        checkpoint()
        if not (p/'idVendor').exists():continue
        name=' · '.join(filter(None,[read(p/'manufacturer'),read(p/'product'),read(p/'idVendor')+':'+read(p/'idProduct')]))
        hub=read(p/'bDeviceClass')=='09'
        add('usb',p.name,name+(' · @hub' if hub else '')+' · @logical',kind='hub' if hub else 'component')
        if re.search(r'card.?reader|sd reader',name,re.I):add('reader',p.name,name+' · @component')
    disks=json_command(['lsblk','--json','--bytes','--output','NAME,TYPE,SIZE,MODEL,TRAN,ROTA,FSTYPE,MOUNTPOINTS'],diagnostics,cancel_event)
    for d in walk_disks(disks.get('blockdevices',[]) if isinstance(disks,dict) else []):
        checkpoint()
        details=[d.get('model') or d['name'],quantity(d.get('size')),d.get('tran') or UNKNOWN, rotation_label(d.get('rota')) if d.get('type')=='disk' else d.get('type',''),d.get('fstype') or '']
        for mount in d.get('mountpoints') or []:
            if mount:
                try:
                    stat=os.statvfs(mount); details.append(f'@used {quantity((stat.f_blocks-stat.f_bfree)*stat.f_frsize)} / {quantity(stat.f_blocks*stat.f_frsize)}')
                except OSError:details.append(UNKNOWN)
        add('disk','/dev/'+d['name'],' · '.join(filter(None,details)),kind='partition' if d.get('type')=='part' else 'drive' if d.get('type')=='disk' else 'logical')
    addresses=json_command(['ip','-j','address'],diagnostics,cancel_event)
    for p in Path('/sys/class/net').glob('*'):
        checkpoint()
        section='wifi' if (p/'wireless').exists() else 'lan'
        virtual=not (p/'device').exists(); driver=(p/'device/driver').resolve().name if (p/'device/driver').exists() else UNKNOWN
        add(section,p.name,f'{read(p/"operstate") or UNKNOWN} · {driver} · '+ ('@virtual' if virtual else '@logical'),kind='virtual' if virtual else 'adapter')
        link=lan_diagnostics(p)
        state_key=link['state'] if link['state'] in ('up','down','dormant','lowerlayerdown','notpresent','testing') else 'unknown'
        add(section,p.name+' / @operstate','@operstate_'+state_key)
        add(section,p.name+' / @link_diagnostic','@'+link['reason'])
        for field in ('carrier_changes','carrier_up_count','carrier_down_count'):
            if field in link:add(section,p.name+' / @'+field,link[field])
        if section=='lan' and not virtual:
            carrier=link['carrier']
            add('lan',p.name+' / @carrier', '@connected' if carrier=='1' else '@disconnected' if carrier=='0' else UNKNOWN)
            speed=read(p/'speed')
            add('lan',p.name+' / @link_speed',speed+' Mbit/s' if speed.isdigit() and int(speed)>0 else UNKNOWN)
        add(section,p.name+' MAC',read(p/'address'),personal=True)
        if isinstance(addresses,list):
            for a in addresses:
                if a.get('ifname')==p.name:
                    for addr in a.get('addr_info',[]):add(section,p.name+' IP',addr.get('local'),personal=True)
        if section=='wifi':
            link=run(['iw','dev',p.name,'link'],diagnostics,cancel_event=cancel_event)
            metrics=wifi_metrics(link)
            add('wifi',p.name+' SSID',metrics['ssid'],personal=True)
            for label in ('signal','rx_bitrate','tx_bitrate'):
                add('wifi',p.name+' / @'+label,metrics[label])
    for p in Path('/sys/class/mmc_host').glob('*'):
        add('reader',p.name,'@logical','unknown')
    for p in Path('/sys/class/bluetooth').glob('*'):
        checkpoint()
        add('bluetooth',p.name,(read(p/'name') or p.name)+' · @component')
    bluetooth=bluez_devices(diagnostics)
    for device in bluetooth or []:
        checkpoint()
        add('bluetooth',device['key'],device['kind']+' · '+device['modalias']+' · '+('@connected' if device['connected'] else '@disconnected'),kind='component')
        add('bluetooth',device['key']+' / alias',device['alias'],personal=True)
        add('bluetooth',device['key']+' / MAC',device['address'],personal=True)
    audio_descriptions={}
    for line in read('/proc/asound/cards').splitlines():
        match=re.match(r'\s*(\d+) \[([^]]+)\]:(.*)',line)
        if match:audio_descriptions['card'+match[1]]=match[3].strip()
    for p in Path('/sys/class/sound').glob('card[0-9]*'):
        checkpoint()
        add('audio',p.name,audio_descriptions.get(p.name) or read(p/'id'))
    if Path('/sys/class/sound').exists():
        for category in ('sinks','sources'):
            endpoints=json_command(['pactl','--format=json','list',category],diagnostics,cancel_event)
            default=run(['pactl','get-default-'+('sink' if category=='sinks' else 'source')],diagnostics,cancel_event=cancel_event).strip()
            for endpoint in endpoints if isinstance(endpoints,list) else []:
                checkpoint()
                index=str(endpoint.get('index','?'));name=str(endpoint.get('name',''))
                prefix=('@audio_output' if category=='sinks' else '@audio_input')+' '+index
                ports=endpoint.get('active_port') or UNKNOWN
                if isinstance(ports,dict):ports=ports.get('name',UNKNOWN)
                add('audio',prefix,' · '.join([str(endpoint.get('state',UNKNOWN)),str(ports),'@default' if default and name==default else '@not_default']),kind='logical')
                # Server descriptions/names may include user-defined identities.
                add('audio',prefix+' / @description',endpoint.get('description') or name,personal=True)
    for p in Path('/sys/class/hwmon').glob('*'):
        checkpoint()
        for sensor in list(p.glob('temp*_input'))+list(p.glob('fan*_input')):
            checkpoint()
            raw=read(sensor)
            try:value=float(raw);value=value/1000 if sensor.name.startswith('temp') else value
            except ValueError:continue
            label=read(sensor.with_name(sensor.name.replace('_input','_label'))) or sensor.stem
            add('sensors',read(p/'name')+' / '+label+' / '+sensor_identity(p),f'{value:g} '+('°C' if sensor.name.startswith('temp') else 'RPM'))
    virt=run(['systemd-detect-virt'],diagnostics,allowed_exits=((1,'none'),),cancel_event=cancel_event).strip()
    virt='@no_virtualization' if virt=='none' else virt or UNKNOWN
    for key,value in [('kernel',os.uname().release),('architecture',os.uname().machine),('os',next((v.split('=',1)[1].strip('"') for v in read('/etc/os-release').splitlines() if v.startswith('PRETTY_NAME=')),'')),('virtualization',virt)]:add('system',key,value)
    for command,state in dict(diagnostics).items():add('system',command,'@'+state)
    for section in SECTIONS[:-1]:
        if not data[section]:add(section,'detection',UNKNOWN,'unknown' if section not in ('cpu','board','sensors','system') else '')
    # Refuse ambiguous identities rather than opening an arbitrary matching row.
    identifiers=[r['device_id'] for group in data.values() for r in group if r.get('device_id')]
    ambiguous={identity for identity in identifiers if identifiers.count(identity)>1}
    for identity in ambiguous:details_by_id.pop(identity,None)
    for group in data.values():
        for record in group:
            if record.get('device_id') in ambiguous:record.pop('device_id',None)
    bank_rows=[r for r in data['ram'] if r.get('slot_id')]
    checkpoint()
    confirmed=bool(bank_rows) and len({r['slot_id'] for r in bank_rows})==len(bank_rows) and all(r['occupancy']=='empty' or (r['occupancy']=='occupied' and r.get('device_id') in details_by_id) for r in bank_rows)
    capture=dict(confirmed=confirmed,captured_at=captured,query_mode=query_mode,status='ram_capture_ok' if confirmed else 'ram_capture_unavailable')
    return dict(firmware_capture=firmware,ram_capture=capture,created=datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %Z'),sections=data,details=details_by_id)


def walk_disks(devices):
    for d in devices:
        yield d
        yield from walk_disks(d.get('children',[]))


def device_state(previous=None):
    """Lightweight polling identities; never infer past events or empty sockets."""
    result={}
    for family,root in [('usb','/sys/bus/usb/devices'),('disk','/sys/class/block'),('bluetooth','/sys/class/bluetooth'),('lan','/sys/class/net'),('display','/sys/class/drm')]:
        for p in Path(root).glob('*'):
            if family=='usb' and not (p/'idVendor').exists():continue
            if family=='display' and not (p/'status').exists():continue
            name=read(p/'product') or read(p/'device/model') or p.name
            # USB devnum changes when the same model is replaced at the same bus path.
            status=read(p/'status') or read(p/'operstate') or read(p/'devnum') or 'present'
            if family=='lan':
                status,carrier=lan_states(p)
                result[('lan_carrier',p.name)]=(name,carrier)
            result[(family,p.name)]=(name,status)
    bluetooth=bluez_devices()
    if bluetooth is None:
        result.update({key:value for key,value in (previous or {}).items() if key[0] in ('bluez','_bluez')})
    else:
        result[('_bluez','ready')]=('','ready')
        for device in bluetooth:
            result[('bluez',device['key'])]=(device['kind'],'connected' if device['connected'] else 'disconnected')
    return result


def differences(old,new):
    changes=[]
    for key in sorted(old.keys() | new.keys()):
        if key[0].startswith('_'):continue
        if key[0]=='bluez' and (('_bluez','ready') not in old or ('_bluez','ready') not in new):continue
        if key[0]=='lan_carrier' and (key not in old or key not in new):continue
        if key not in old:kind='attached';value=new[key]
        elif key not in new:kind='removed';value=old[key]
        elif old[key]!=new[key]:
            value=new[key];kind='operational_changed' if key[0]=='lan' else 'changed'
            if key[0] in ('lan_carrier','display','bluez'):
                kind='connected' if value[1] in ('up','connected') else 'disconnected' if value[1] in ('down','disconnected','lowerlayerdown') else 'changed'
        else:continue
        changes.append(dict(time=datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S'),kind=kind,device=value[0],connector=key[1],state=value[1]))
    return changes


def report(snapshot,tr,events=(),personal=False,events_omitted=0):
    lines=['pcmonitor',tr('created')+': '+snapshot['created'],tr('limits'),'']
    for section,rows in snapshot['sections'].items():
        if section=='events':continue
        lines.extend([tr('section_'+section),'-'*40])
        if section=='ram' and snapshot.get('ram_capture'):
            capture=snapshot['ram_capture']
            lines.extend([tr(capture['status']),tr('details_recorded')+': '+capture.get('captured_at',UNKNOWN),tr('ram_query_mode')+': '+tr(capture.get('query_mode','ram_mode_normal'))])
        for r in rows:
            if r['personal'] and not personal:continue
            value=translate_value(r['value'],tr)
            name=translate_value(tr(r['name']),tr)
            if not personal:name,value=redact(name),redact(value)
            if r.get('kind') not in (None,'property'):name+=' ['+tr('kind_'+r['kind'])+']'
            line=name+(f': {value}' if value else '')+(f" | {tr('occupancy_'+r['occupancy'])}" if r['occupancy'] else '')
            lines.append(line if personal else redact(line))
        for r in rows:
            detail=snapshot.get('details',{}).get(r.get('device_id'))
            if not detail:continue
            lines.append(tr('device_details')+': '+redact(detail['name']) if not personal else tr('device_details')+': '+detail['name'])
            for key,value in detail['fields'].items():
                if key=='serial' and not personal:continue
                text=tr(key)+': '+translate_value(str(value),tr)
                lines.append(text if personal else redact(text))
        lines.append('')
    if events or events_omitted:
        lines.append(tr('section_events'))
        if events:
            lines.append(tr('events_coverage').format(start=events[0]['time'],end=events[-1]['time']))
        if events_omitted:
            lines.append(tr('events_omitted').format(count=events_omitted))
        for e in events:
            if e.get('personal') and not personal:continue
            line=f"{e['time']} | {tr(e['kind'])} | {e['device']} | {e['connector']} | {e['state']}"
            lines.append(line if personal else redact(line))
    return '\n'.join(lines)+'\n'


def translate_value(value,tr):
    return re.sub(r'@([a-z_]+)\b',lambda m:tr(m[1]),value)
