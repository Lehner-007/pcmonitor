import subprocess
import unittest
from unittest.mock import patch
from modules.inventory import differences,inventory,report,row,run,SECTIONS,rotation_label,retain_events

class InventoryTests(unittest.TestCase):
    def setUp(self):
        firmware=patch('modules.inventory.query_memory_firmware',return_value=dict(captured_at='10.10.2026 12:00:00',devices={},warning='',status='ram_fw_missing'))
        firmware.start();self.addCleanup(firmware.stop)
        bluez=patch('modules.inventory.bluez_devices',return_value=[])
        bluez.start();self.addCleanup(bluez.stop)
    def test_sensitive_opt_in(self):
        s=dict(created='10.10.2026',sections={'lan':[row('model','adapter'),row('MAC','SECRET_MAC',personal=True),row('IP','SECRET_IP',personal=True),row('SSID','SECRET_SSID',personal=True)]})
        self.assertNotIn('SECRET',report(s,lambda x:x))
        self.assertIn('SECRET_MAC',report(s,lambda x:x,personal=True))
    def test_events_no_retroactive_changes(self):
        before={('usb','1-1'):('device','1')}
        self.assertEqual(differences(before,before),[])
        self.assertEqual(differences({},before)[0]['kind'],'attached')
        self.assertEqual(differences(before,{})[0]['kind'],'removed')
        self.assertEqual(differences(before,{('usb','1-1'):('device','2')})[0]['kind'],'changed')
    def test_missing_and_timeout(self):
        diagnostics=[]
        with patch('modules.inventory.shutil.which',return_value=None):self.assertEqual(run(['absent'],diagnostics),'')
        self.assertEqual(diagnostics,[('absent','missing')])
        with patch('modules.inventory.shutil.which',return_value='/bin/tool'),patch('modules.inventory.run_capped',return_value=('timeout',None,'','')):
            self.assertEqual(run(['tool'],diagnostics),'')
        self.assertEqual(diagnostics[-1],('tool','timeout'))
    def test_rotation_values_keep_unknown_explicit(self):
        self.assertEqual([rotation_label(v) for v in (True,False,1,0,None)],['HDD','@nonrotating','HDD','@nonrotating','@unknown'])
        self.assertEqual(rotation_label('0'),'@unknown')
        self.assertEqual(rotation_label('false'),'@unknown')
        self.assertEqual(rotation_label(2),'@unknown')
    def test_event_buffer_reports_omitted_entries_and_coverage(self):
        from collections import deque
        events=deque(maxlen=3)
        first=[dict(time='22.10.2026 10:00:00',kind='attached',device='a',connector='1',state='up'),
               dict(time='22.10.2026 10:01:00',kind='attached',device='b',connector='2',state='up')]
        self.assertEqual(retain_events(events,first,3),0)
        later=[dict(time='22.10.2026 10:02:00',kind='removed',device='a',connector='1',state='down'),
               dict(time='22.10.2026 10:03:00',kind='removed',device='b',connector='2',state='down')]
        self.assertEqual(retain_events(events,later,3),1)
        tr=lambda key: {'section_events':'Ereignisse','events_count':'Gespeichert: {count}','events_coverage':'Abdeckung: {start} bis {end}','events_omitted':'Ausgelassen: {count}'}.get(key,key)
        text=report(dict(created='22.10.2026',sections={}),tr,events,events_omitted=1)
        self.assertIn('Abdeckung: 22.10.2026 10:01:00 bis 22.10.2026 10:03:00',text)
        self.assertIn('Ausgelassen: 1',text)
    def test_inventory_without_optional_tools(self):
        with patch('modules.inventory.shutil.which',return_value=None):s=inventory()
        self.assertEqual(tuple(s['sections']),SECTIONS)
        for section in SECTIONS[:-1]:self.assertTrue(s['sections'][section])
        # Absent physical devices must never imply an empty socket.
        self.assertFalse(any(r['occupancy']=='empty' for rows in s['sections'].values() for r in rows))
    def test_ram_explicit_empty_evidence(self):
        hw={'id':'memory','children':[{'id':'bank:0','slot':'A1','description':'DIMM [empty]'}, {'id':'bank:1','slot':'A2','size':17179869184,'vendor':'Example','product':'Module','clock':3200000000}]}
        def command(args,diagnostics,*_):return hw if args[0]=='lshw' else {}
        with patch('modules.inventory.json_command',side_effect=command),patch('modules.inventory.run',return_value=''):
            s=inventory()
        rows={r['name']:r for r in s['sections']['ram']}
        self.assertEqual(rows['A1']['occupancy'],'empty')
        self.assertEqual(rows['A2']['occupancy'],'occupied')
        self.assertIn('16.00 GiB',rows['A2']['value'])

    def test_ram_capture_metadata_normal_and_admin(self):
        import json
        bank={'id':'bank:0','slot':'A1','size':1024,'product':'Module','serial':'PRIVATE'}
        def command(args,diagnostics,*_):return bank if args[0]=='lshw' else {}
        with patch.dict('os.environ',{'PCMONITOR_ADMIN_QUERY':'0'}),patch('modules.inventory.json_command',side_effect=command),patch('modules.inventory.run',return_value=''):
            normal=inventory()
        self.assertTrue(normal['ram_capture']['confirmed'])
        detail=next(d for d in normal['details'].values() if d['family']=='ram')
        self.assertEqual(detail['captured_at'],normal['ram_capture']['captured_at'])
        self.assertEqual(detail['query_mode'],'ram_mode_normal')
        self.assertEqual(detail['occupancy'],'occupied')
        self.assertTrue(detail['slot_id'])
        def query(args,*a,**k):return json.dumps(bank) if args[0]=='pkexec' else ''
        with patch.dict('os.environ',{'PCMONITOR_ADMIN_QUERY':'1'}),patch('modules.inventory.query_admin_sources',return_value=dict(status='ok',sources={'lshw':dict(status='ok',stdout=json.dumps(bank),captured_at='10.10.2026 12:00:00')})),patch('modules.inventory.run',return_value=''):
            admin=inventory()
        self.assertTrue(admin['ram_capture']['confirmed'])
        self.assertEqual(admin['ram_capture']['query_mode'],'ram_mode_admin')

    def test_failed_admin_independent_of_installed_files(self):
        def command(args,diagnostics,*_):return {'id':'memory'} if args[0]=='lshw' else {}
        with patch.dict('os.environ',{'PCMONITOR_ADMIN_QUERY':'1'}),patch('modules.inventory.query_admin_sources',return_value=dict(status='denied',sources={})),patch('modules.inventory.run',return_value=''),patch('modules.inventory.json_command',side_effect=command) as fallback:
            snapshot=inventory()
        self.assertEqual(snapshot['ram_capture']['query_mode'],'ram_mode_fallback')
        self.assertTrue(any(call.args[0][0]=='lshw' for call in fallback.call_args_list))

    def test_missing_admin_lshw_separate_from_rejection(self):
        with patch.dict('os.environ',{'PCMONITOR_ADMIN_QUERY':'1'}),patch('modules.inventory.query_admin_sources',return_value=dict(status='ok',sources={'lshw':dict(status='missing',stdout='',captured_at='10.10.2026')})),patch('modules.inventory.run',return_value='') as run,patch('modules.inventory.json_command',return_value={}):
            inventory()
        self.assertFalse(any(call.args[0][0]=='pkexec' for call in run.call_args_list))

if __name__=='__main__':unittest.main()
