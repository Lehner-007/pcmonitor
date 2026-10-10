"""Session-only RAM snapshots. No file persistence and no hardware queries."""
from copy import deepcopy
from .ram_firmware import sync_ram_row


def merge_snapshot(previous, incoming):
    """Atomically choose a complete confirmed RAM generation or retain the old one."""
    if incoming is None:
        if previous is None:return None
        result=deepcopy(previous)
    else:result=deepcopy(incoming)
    old=(previous or {}).get('ram_capture',{})
    new=(incoming or {}).get('ram_capture',{})
    old_slots={r.get('slot_id') for r in (previous or {}).get('sections',{}).get('ram',[]) if r.get('slot_id')}
    new_slots={r.get('slot_id') for r in (incoming or {}).get('sections',{}).get('ram',[]) if r.get('slot_id')}
    complete=new.get('confirmed') and (not old.get('confirmed') or old_slots<=new_slots)
    if complete:
        for identity,detail in result.get('details',{}).items():
            if detail['family']!='ram':continue
            fresh=detail.get('firmware');prior=(previous or {}).get('details',{}).get(identity,{}).get('firmware')
            if fresh and fresh['status']!='ram_fw_ok' and prior and prior['status'] in ('ram_fw_ok','ram_fw_old'):
                failed_status=fresh['status']
                detail['firmware']=deepcopy(prior);detail['firmware']['status']='ram_fw_old'
                detail['firmware']['fields']['ram_firmware_status']='@ram_fw_old · @'+failed_status
                detail['fields'].update(detail['firmware']['fields'])
            for record in result['sections']['ram']:
                if record.get('device_id')==identity:sync_ram_row(record,detail)
        return result
    if old.get('confirmed'):
        result['sections']['ram']=deepcopy(previous['sections']['ram'])
        result['details']={k:v for k,v in result.get('details',{}).items() if v['family']!='ram'}
        result['details'].update(deepcopy({k:v for k,v in previous.get('details',{}).items() if v['family']=='ram'}))
        result['ram_capture']={**deepcopy(old),'status':'ram_capture_old'}
        for detail in result['details'].values():
            if detail['family']=='ram':detail['capture_status']='ram_capture_old'
    else:
        result['ram_capture']={**new,'confirmed':False,'status':'ram_capture_unavailable'}
    return result
