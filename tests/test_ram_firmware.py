import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from modules.ram_firmware import parse_memory_devices,query_memory_firmware,module_firmware
from modules.ram_snapshot import merge_snapshot
from modules.inventory import inventory,report
from test_ram_snapshot import generation

FIXTURE=(Path(__file__).parent/'fixtures/ram_ddr5_dmidecode.txt').read_text()

class FirmwareTests(unittest.TestCase):
    def result(self,code=0,text=FIXTURE):return SimpleNamespace(returncode=code,stdout=text,stderr='')
    def source(self):
        return query_memory_firmware(True,source=dict(status='ok',stdout=FIXTURE,stderr='',captured_at='10.10.2026 12:00:05'))

    def test_anonymized_real_output_exact_slots_and_units(self):
        records=parse_memory_devices(FIXTURE)
        for slot in ('DIMMA2','DIMMB2'):
            self.assertEqual(records[slot]['fields'],dict(ram_configured_rate='6000 MT/s',ram_reported_speed='6000 MT/s'))
        for slot in ('DIMMA1','DIMMB1'):self.assertEqual(records[slot]['status'],'ram_fw_empty')
        source=self.source();self.assertEqual(source['status'],'ram_fw_ok')
        self.assertIn('@ram_fw_smbios_warning',source['warning'])
        self.assertIn('SMBIOS 3.8.0',source['warning'])
        self.assertEqual(module_firmware(source,'dimma2')['status'],'ram_fw_unmatched')

    def test_normal_and_elevated_queries(self):
        with patch('modules.ram_firmware.shutil.which',return_value='/fixture/dmidecode'),patch('modules.ram_firmware.run_capped',return_value=('ok',0,FIXTURE,'')) as run:
            query_memory_firmware(False)
        self.assertEqual(run.call_args.args[0],['/fixture/dmidecode','--type','17'])
        with patch('modules.ram_firmware.run_capped',side_effect=AssertionError('second privilege request')):
            source=self.source()
        self.assertEqual(source['status'],'ram_fw_ok')

    def test_missing_tools(self):
        with patch('modules.ram_firmware.shutil.which',return_value=None):
            self.assertEqual(query_memory_firmware(False)['status'],'ram_fw_missing')
        self.assertEqual(query_memory_firmware(True,admin_status='missing')['status'],'ram_fw_admin_missing')
        self.assertEqual(query_memory_firmware(True,source=dict(status='missing',captured_at='10.10.2026',stdout=''))['status'],'ram_fw_missing')

    def test_denied_timeout_failed_and_incomplete(self):
        for status,expected in [('denied','ram_fw_denied'),('cancelled','ram_fw_denied'),('timeout','ram_fw_timeout'),('failed','ram_fw_failed')]:
            self.assertEqual(query_memory_firmware(True,admin_status=status)['status'],expected)
        self.assertEqual(query_memory_firmware(True,source=dict(status='ok',captured_at='10.10.2026',stdout='',stderr=''))['status'],'ram_fw_incomplete')

    def test_configured_and_rated_separate_no_unit_conversion(self):
        text='Handle 0x0\nMemory Device\n Locator: A\n Speed: 6000 MT/s\n Configured Memory Speed: 2400 MHz\n'
        fields=parse_memory_devices(text)['A']['fields']
        self.assertEqual(fields['ram_configured_rate'],'2400 MHz')
        self.assertEqual(fields['ram_reported_speed'],'6000 MT/s')
        missing=parse_memory_devices(text.replace(' Configured Memory Speed: 2400 MHz\n',''))['A']
        self.assertEqual(missing['fields']['ram_configured_rate'],'@unknown')
        self.assertEqual(missing['status'],'ram_fw_incomplete')

    def test_duplicate_locator_and_conflicting_fields(self):
        block='Handle 0x0\nMemory Device\n Locator: A\n Speed: 6000 MT/s\n Configured Memory Speed: 6000 MT/s\n'
        self.assertEqual(parse_memory_devices(block+block)['A']['status'],'ram_fw_conflict')
        self.assertEqual(parse_memory_devices(block+' Configured Memory Speed: 4800 MT/s\n')['A']['fields']['ram_configured_rate'],'@unknown')

    def test_firmware_failure_does_not_discard_lshw_banks(self):
        hw={'id':'memory','children':[{'id':'bank:'+str(i),'slot':slot,'description':'DIMM [empty]' if i%2==0 else 'DIMM DDR5','size':None if i%2==0 else 17179869184,'product':'KF560C30-16','vendor':'Kingston','serial':'ANON-'+slot,'clock':1705032704} for i,slot in enumerate(('DIMMA1','DIMMA2','DIMMB1','DIMMB2'))]}
        def command(args,diagnostics,*_):return hw if args[0]=='lshw' else {}
        for source in (self.source(),dict(status='ram_fw_denied',devices={},captured_at='10.10.2026 12:00:00',warning='')):
            with patch.dict('os.environ',{'PCMONITOR_ADMIN_QUERY':'0'}),patch('modules.inventory.query_memory_firmware',return_value=source),patch('modules.inventory.json_command',side_effect=command),patch('modules.inventory.run',return_value=''),patch('modules.inventory.bluez_devices',return_value=[]):snapshot=inventory()
            self.assertTrue(snapshot['ram_capture']['confirmed'])
            banks=[r for r in snapshot['sections']['ram'] if r.get('slot_id')]
            self.assertEqual([r['occupancy'] for r in banks],['empty','occupied','empty','occupied'])
            for detail in snapshot['details'].values():
                if detail['family']!='ram':continue
                self.assertIn('1705032704',detail['fields']['module_speed'])
                self.assertEqual(detail['fields']['ram_configured_rate'],'6000 MT/s' if source['status']=='ram_fw_ok' else '@unknown')
            for bank in banks:
                self.assertNotIn('1705032704',bank['value'])
                self.assertNotIn('ram_reported_speed',bank['value'])
                if bank['occupancy']=='occupied':
                    self.assertIn('6000 MT/s' if source['status']=='ram_fw_ok' else '@unknown',bank['value'])
            self.assertNotIn('ANON-',report(snapshot,lambda key:key))
            self.assertIn('ANON-DIMMA2',report(snapshot,lambda key:key,personal=True))

    def test_preserve_previous_firmware_only_for_same_module(self):
        previous=generation();prior=previous['details']['ram:A'];prior['firmware']=module_firmware(self.source(),'DIMMA2');prior['fields'].update(prior['firmware']['fields'])
        fresh=generation('10.10.2026 14:00:00');fresh['details']['ram:A']['firmware']=module_firmware(dict(status='ram_fw_denied',devices={},captured_at='10.10.2026 14:00:00',warning=''),'DIMMA2');fresh['details']['ram:A']['fields'].update(fresh['details']['ram:A']['firmware']['fields'])
        merged=merge_snapshot(previous,fresh);detail=merged['details']['ram:A']
        self.assertEqual(detail['captured_at'],'10.10.2026 14:00:00')
        self.assertEqual(detail['firmware']['captured_at'],prior['firmware']['captured_at'])
        self.assertEqual(detail['firmware']['status'],'ram_fw_old')
        self.assertEqual(detail['fields']['ram_configured_rate'],'6000 MT/s')
        self.assertIn('ram_fw_denied',detail['fields']['ram_firmware_status'])
        changed=generation(module='B');changed['details']['ram:B']['firmware']=fresh['details']['ram:A']['firmware']
        self.assertEqual(merge_snapshot(previous,changed)['details']['ram:B']['firmware']['status'],'ram_fw_denied')

class RamOverviewTests(unittest.TestCase):
    def test_configured_rate_never_substitutes_reported_speed(self):
        from modules.ram_firmware import sync_ram_row
        for status,rate in [('ram_fw_incomplete','@unknown'),('ram_fw_conflict','6000 MT/s'),('ram_fw_old','6000 MT/s')]:
            row=dict(value='1705032704 Hz')
            detail=dict(fields=dict(manufacturer='Kingston',model='KF560C30-16',module_capacity='16 GiB'),firmware=dict(status=status,captured_at='10.10.2026 12:00:00',fields=dict(ram_configured_rate=rate,ram_reported_speed='6400 MT/s')))
            sync_ram_row(row,detail)
            self.assertNotIn('1705032704',row['value']);self.assertNotIn('6400',row['value'])
            if status=='ram_fw_old':
                self.assertIn('6000 MT/s',row['value']);self.assertIn('10.10.2026 12:00:00',row['value'])
            else:self.assertIn('@unknown',row['value'])
