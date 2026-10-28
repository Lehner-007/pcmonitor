"""Parsing and conservative matching of optional, read-only hardware sources."""
import csv
import hashlib
import re
from pathlib import Path

UNKNOWN='@unknown'


def cpu_set(text):
    result=set()
    try:
        for part in text.strip().split(','):
            bounds=[int(x) for x in part.split('-')]
            if len(bounds)==1:result.add(bounds[0])
            elif len(bounds)==2 and 0<=bounds[0]<=bounds[1]<65536:result.update(range(bounds[0],bounds[1]+1))
            else:return set()
    except ValueError:return set()
    return result


def pci_address(value, function=True):
    """Canonicalize 16/32-bit PCI domains, without conflating functions."""
    match=re.fullmatch(r'([0-9a-fA-F]{4,8}):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})(?:\.([0-7]))?',value.strip())
    if not match:return ''
    domain,bus,device,fn=match.groups()
    base=f'{int(domain,16):04x}:{bus.lower()}:{device.lower()}'
    return base+('.'+fn if fn is not None else '') if function else base


def slot_matches(address, devices):
    target=pci_address(address,function=False)
    return [d for d in devices if target and pci_address(d.name,function=False)==target]


def nvidia_memory(text):
    result={}
    for fields in csv.reader(text.splitlines()):
        if len(fields)!=2:continue
        address=pci_address(fields[0])
        try:memory=float(fields[1].strip())
        except ValueError:continue
        if address and 0<memory<10**8:result[address]=int(memory*1024*1024)
    return result


def dmidecode_speeds(text):
    """Only explicitly unit-labelled speeds, associated with an exact locator."""
    result={}
    for block in re.split(r'\n(?=Handle )',text):
        values=dict(re.findall(r'^\s*([^:\n]+):\s*(.*?)\s*$',block,re.M))
        locator=values.get('Locator')
        speed=values.get('Configured Memory Speed') or values.get('Configured Clock Speed') or values.get('Speed')
        match=re.fullmatch(r'(\d+) (MT/s|MHz)',speed or '')
        if locator and match and 1<=int(match[1])<=20000:
            # Duplicated locators cannot be matched safely.
            result[locator]=speed if locator not in result else UNKNOWN
    return result


def ram_speed(bank,speeds):
    explicit=speeds.get(bank.get('slot'))
    if explicit:return explicit+' · dmidecode'
    desc=bank.get('description','')
    match=re.search(r'\b(\d+)\s*MT/s\b',desc)
    if match and 1<=int(match[1])<=20000:return match[0]+' · lshw'
    clock=bank.get('clock')
    if not clock:return UNKNOWN
    # lshw's field has no reliable MT/s/MHz provenance. Never undo overflow
    # by adding 2**32, and never relabel this number as a measured data rate.
    try:
        clock=int(clock)
        if clock<=0 or clock>20_000_000_000 or clock%1_000_000:
            return '@ram_suspect ('+str(clock)+' Hz; lshw)'
    except (ValueError,TypeError):return '@ram_suspect'
    return '@ram_unverified ('+f'{clock/1_000_000:g}'+' MHz; lshw)'


def xrandr_outputs(text):
    outputs=[]
    for block in re.split(r'(?=^\S+ (?:connected|disconnected)\b)',text,flags=re.M):
        header=re.match(r'(\S+) (connected|disconnected)\b',block)
        if not header:continue
        edid_match=re.search(r'^\s+EDID:\s*\n((?:\s+[0-9a-fA-F]{32}\s*\n)+)',block,re.M)
        edid=bytes.fromhex(''.join(edid_match[1].split())) if edid_match else b''
        mode=re.search(r'^\s+(\d+x\d+)\s+[^\n]*?([\d.]+)\*',block,re.M)
        modes=[]
        for entry in re.finditer(r'^\s+(\d+x\d+)\s+([^\n]+)',block,re.M):
            rates=re.findall(r'(\d+(?:\.\d+)?)[*+]*(?:\s|$)',entry[2])
            if rates:modes.append(entry[1]+' / '+', '.join(rates)+' Hz')
        outputs.append(dict(modes=modes,name=header[1],connected=header[2]=='connected',edid=edid,
                            mode=(mode[1]+' / '+mode[2]+' Hz') if mode else UNKNOWN))
    return outputs


def valid_edid(edid):
    return bool(edid) and len(edid)%128==0 and edid[:8]==b'\x00\xff\xff\xff\xff\xff\xff\x00' and all(sum(edid[i:i+128])%256==0 for i in range(0,len(edid),128))


def match_monitor(connector,all_connectors,outputs):
    """EDID must be unique on both sides; names alone are not GPU identities."""
    if connector['status']!='connected' or not valid_edid(connector['edid']):return None
    edid=connector['edid']
    if sum(c['status']=='connected' and c['edid']==edid for c in all_connectors)!=1:return None
    matches=[o for o in outputs if o['connected'] and o['edid']==edid]
    return matches[0] if len(matches)==1 else None


def bluez_devices(diagnostics=None):
    """BlueZ system D-Bus query. Never pair/connect/change settings."""
    try:
        from gi.repository import Gio,GLib
    except ImportError:
        if diagnostics is not None:diagnostics.append(('BlueZ','unavailable'))
        return None
    try:
        bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
        response=bus.call_sync('org.bluez','/','org.freedesktop.DBus.ObjectManager','GetManagedObjects',None,None,Gio.DBusCallFlags.NONE,2000,None)
        objects=response.unpack()[0]
        return parse_bluez(objects)
    except (GLib.Error,TypeError,ValueError,KeyError,AttributeError):
        # D-Bus absence/denial is optional hardware support; no traceback or
        # device properties are logged. Unavailability is distinct from [].
        if diagnostics is not None:diagnostics.append(('BlueZ','unavailable'))
        return None


def parse_bluez(objects):
    devices=[]
    for path,interfaces in objects.items():
        props=interfaces.get('org.bluez.Device1')
        if props is None:continue
        adapter=str(props.get('Adapter','')).rsplit('/',1)[-1]
        token=hashlib.sha256(path.encode()).hexdigest()[:12]
        devices.append(dict(key=adapter+':device-'+token,connected=bool(props.get('Connected')),alias=str(props.get('Alias') or ''),address=str(props.get('Address') or ''),kind=str(props.get('Icon') or 'Bluetooth'),modalias=str(props.get('Modalias') or UNKNOWN)))
    return devices


def wifi_metrics(text):
    metrics={}
    for label,pattern in [('ssid',r'^\s*SSID: ([^\n]+)'),('signal',r'signal: ([^\n]+)'),('rx_bitrate',r'rx bitrate: ([^\n]+)'),('tx_bitrate',r'tx bitrate: ([^\n]+)')]:
        match=re.search(pattern,text,re.M)
        metrics[label]=match[1].strip() if match else UNKNOWN
    return metrics


def slot_occupants(address,devices,read):
    # A permanently present PCI bridge/root port does not prove a plugged card.
    return [p for p in slot_matches(address,devices) if read(p/'class') and not read(p/'class').startswith('0x0604')]


def sensor_origin(path):
    resolved=(path/'device').resolve()
    return str(resolved) if (path/'device').exists() else str(path.resolve())


def occupancy_matches(record, selected):
    """Filters apply only to rows for which occupancy is meaningful."""
    return selected == 'all' or not record.get('occupancy') or record['occupancy'] == selected


def lan_states(path):
    def read_field(name):
        try:return (path/name).read_text().strip()
        except OSError:return ''
    carrier=read_field('carrier') if (path/'device').exists() else ''
    return read_field('operstate') or 'unknown', {'1':'connected','0':'disconnected'}.get(carrier,'unknown')


def lan_diagnostics(path):
    """Return read-only kernel link state and counters without inferring a cause."""
    path=Path(path)
    def read_field(name):
        try:return (path/name).read_text().strip()
        except OSError:return ''
    state=(read_field('operstate') or 'unknown').lower()
    carrier=read_field('carrier') if (path/'device').exists() else ''
    dormant=read_field('dormant')
    if state=='up' and carrier=='1':reason='link_detected'
    elif state=='down' and carrier=='0':reason='no_carrier'
    elif state=='dormant' or dormant=='1':reason='link_dormant'
    elif state=='lowerlayerdown':reason='lower_layer_down'
    elif state=='down':reason='interface_down'
    elif state=='notpresent':reason='device_not_present'
    elif state=='up':reason='interface_up_link_unconfirmed'
    else:reason='state_unconfirmed'
    result={'state':state,'carrier':carrier,'reason':reason}
    for field in ('carrier_changes','carrier_up_count','carrier_down_count'):
        value=read_field(field)
        if value.isdigit():result[field]=value
    return result


def sensor_identity(path):
    """Show available device/model names, retaining the unambiguous sysfs origin."""
    origin=Path(sensor_origin(path))
    names=[]
    for parent in (origin, *list(origin.parents)[:3]):
        for field in ('model','product_name'):
            try:value=(parent/field).read_text().strip()
            except OSError:continue
            if value and value not in names:names.append(value)
    return ' / '.join([origin.name, *names, str(origin)])


def redact(text):
    """Defence in depth for device names and event text, not only marked fields."""
    text=re.sub(r'(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])','[MAC]',str(text))
    text=re.sub(r'(?i)dev_(?:[0-9a-f]{2}_){5}[0-9a-f]{2}','[Bluetooth device]',text)
    text=re.sub(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])','[IP]',text)
    # IPv6 sequences have >= 2 colons; PCI BDF strings include a dot and
    # cannot match the required end boundary.
    import ipaddress
    pattern=r'(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F]{0,4}(?:%[\w.-]+)?(?![\w:.])'
    def replace(match):
        try:ipaddress.IPv6Address(match[0].split('%')[0]);return '[IP]'
        except ValueError:return match[0]
    return re.sub(pattern,replace,text)
