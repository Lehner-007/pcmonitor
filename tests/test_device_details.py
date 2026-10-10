import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from modules.device_details import eligible,edid_fields,monitor_detail,current_state,bank_identity
from modules.hardware_sources import xrandr_outputs,match_monitor
from modules.inventory import report,row


def edid(seed=1):
    value=bytearray(128);value[:8]=b'\0\xff\xff\xff\xff\xff\xff\0'
    value[8:10]=((1<<10)|(3<<5)|13).to_bytes(2,'big')
    value[12:16]=seed.to_bytes(4,'little');value[21:23]=bytes([52,29])
    value[54:72]=b'\0\0\0\xfc\0'+b'Same Model\n  '
    value[127]=(-sum(value))%256
    return bytes(value)


class DetailTests(unittest.TestCase):
    def test_only_occupied_associated_devices(self):
        self.assertTrue(eligible(dict(occupancy='occupied',device_id='a')))
        for state in ('empty','unknown','',None):self.assertFalse(eligible(dict(occupancy=state,device_id='a')))
        self.assertFalse(eligible(dict(occupancy='occupied')))

    def test_edid_available_and_missing_fields(self):
        fields=edid_fields(edid())
        self.assertEqual(fields['manufacturer'],'ACM');self.assertEqual(fields['model'],'Same Model')
        self.assertEqual(fields['serial'],'1');self.assertIn('@approx',fields['diagonal'])
        self.assertEqual(edid_fields(b'broken')['dimensions'],'@unknown')
        value=bytearray(edid());value[21:23]=b'\0\0';value[127]=0;value[127]=(-sum(value))%256
        self.assertEqual(edid_fields(bytes(value))['diagonal'],'@unknown')

    def test_active_and_supported_modes_separate(self):
        outputs=xrandr_outputs('HDMI-1 connected\n   1920x1080 60.00*+ 59.94\n   1280x720 60.00\n')
        self.assertEqual(outputs[0]['mode'],'1920x1080 / 60.00 Hz')
        self.assertEqual(outputs[0]['modes'],['1920x1080 / 60.00, 59.94 Hz','1280x720 / 60.00 Hz'])

    def test_same_name_monitors_and_ambiguous_edid(self):
        connectors=[dict(name=f'card{i}-HDMI-A-1',path=f'/unused/{i}',gpu=f'gpu{i}',status='connected',edid=edid(i+1)) for i in range(2)]
        outputs=[dict(name=f'HDMI-{i}',connected=True,edid=c['edid'],mode=str(i),modes=[str(i)]) for i,c in enumerate(connectors)]
        details=[monitor_detail(c,match_monitor(c,connectors,outputs)) for c in connectors]
        self.assertEqual(details[0]['name'],details[1]['name']);self.assertNotEqual(details[0]['id'],details[1]['id'])
        self.assertEqual(details[1]['fields']['active_mode'],'1')
        connectors[1]['edid']=connectors[0]['edid']
        self.assertIsNone(match_monitor(connectors[0],connectors,outputs))
        self.assertEqual(monitor_detail(connectors[0],None)['fields']['active_mode'],'@unknown')

    def test_monitor_removal_and_replacement(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path=Path(directory);(path/'status').write_text('connected');(path/'edid').write_bytes(edid())
            detail=monitor_detail(dict(name='card0-HDMI-A-1',path=path,gpu='gpu',edid=edid()),None)
            self.assertTrue(current_state(detail))
            (path/'edid').write_bytes(edid(2));self.assertFalse(current_state(detail))
            (path/'edid').write_bytes(edid());(path/'status').write_text('disconnected');self.assertFalse(current_state(detail))

    def test_pci_device_removed_or_replaced(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            p=Path(directory);(p/'vendor').write_text('0x1234');(p/'device').write_text('0xabcd')
            detail=dict(family='pci',devices=[dict(path=str(p),vendor='0x1234',device='0xabcd')])
            self.assertTrue(current_state(detail))
            (p/'device').write_text('0x0001');self.assertFalse(current_state(detail))
        self.assertFalse(current_state(detail))

    def test_connected_monitor_without_edid(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            p=Path(directory);(p/'status').write_text('connected');(p/'edid').write_bytes(b'')
            detail=monitor_detail(dict(name='card0-DP-1',path=p,gpu='gpu',edid=b''),None)
            self.assertTrue(current_state(detail))
            self.assertEqual(detail['fields']['active_mode'],'@unknown')
            (p/'status').write_text('');self.assertIsNone(current_state(detail))

    def test_edid_partial_modes_never_active(self):
        value=bytearray(edid());d=bytearray(18)
        d[:2]=(14850).to_bytes(2,'little');d[2]=128;d[3]=24;d[4]=113
        d[5]=56;d[6]=45;d[7]=64
        value[72:90]=d;value[127]=0;value[127]=(-sum(value))%256
        detail=monitor_detail(dict(name='card0-DP-1',path='/unused',gpu='gpu',edid=bytes(value)),None)
        self.assertIn('1920x1080 / 60.00 Hz',detail['fields']['supported_modes'])
        self.assertIn('@edid_modes_partial',detail['fields']['supported_modes'])
        self.assertEqual(detail['fields']['active_mode'],'@unknown')

    def test_detail_serial_only_in_personal_export(self):
        item=row('Monitor','Monitor','occupied');item['device_id']='monitor'
        snap=dict(created='10.10.2026',sections={'display':[item]},details={'monitor':dict(name='Monitor',fields={'serial':'SECRET123','active_mode':'1920x1080'})})
        self.assertNotIn('SECRET123',report(snap,lambda k:k))
        self.assertIn('SECRET123',report(snap,lambda k:k,personal=True))
        self.assertIn('1920x1080',report(snap,lambda k:k))
