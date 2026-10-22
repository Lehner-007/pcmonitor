import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from modules.hardware_sources import (cpu_set,pci_address,slot_matches,nvidia_memory,
    dmidecode_speeds,ram_speed,xrandr_outputs,match_monitor,redact,sensor_origin,parse_bluez,wifi_metrics,slot_occupants)
from modules.inventory import run,report,row,differences,device_state


def edid(seed=1):
    value=bytearray(128);value[:8]=b'\x00\xff\xff\xff\xff\xff\xff\x00';value[10]=seed
    value[127]=(-sum(value))%256
    return bytes(value)


class SourceTests(unittest.TestCase):
    def test_cpu_sets(self):
        self.assertEqual(cpu_set('0-3,8,10-11'),{0,1,2,3,8,10,11})
        self.assertEqual(cpu_set('0-999999'),set())
        self.assertEqual(cpu_set('bad'),set())

    def test_ram_no_overflow_repair(self):
        result=ram_speed({'clock':1705032704},{})
        self.assertIn('@ram_suspect',result)
        self.assertNotIn('6000',result)
        self.assertIn('@ram_unverified',ram_speed({'clock':6000000000},{}))

    def test_ram_explicit_units_and_exact_locator(self):
        text='Handle 0x0010\nMemory Device\n\tLocator: A1\n\tSpeed: 6400 MT/s\n\tConfigured Memory Speed: 6000 MT/s\n'
        speeds=dmidecode_speeds(text)
        self.assertEqual(ram_speed({'slot':'A1','clock':1705032704},speeds),'6000 MT/s · dmidecode')
        self.assertEqual(ram_speed({'slot':'A2'},speeds),'@unknown')
        self.assertEqual(ram_speed({'description':'DDR5 6000 MT/s'},{}),'6000 MT/s · lshw')
        self.assertEqual(dmidecode_speeds(text+'\nHandle 0x0011\n\tLocator: A1\n\tSpeed: 3200 MHz\n')['A1'],'@unknown')
        self.assertEqual(dmidecode_speeds(text.replace('6000 MT/s','6000 Hz')).get('A1'),None)

    def test_nvidia_pci_mapping_and_units(self):
        result=nvidia_memory('00000000:01:00.0, 8192\n00000000:02:00.0, 16384\ninvalid, 8\n0000:03:00.0, N/A\n')
        self.assertEqual(result,{'0000:01:00.0':8192*1024**2,'0000:02:00.0':16384*1024**2})
        self.assertEqual(pci_address('00000000:01:00.1'),'0000:01:00.1')
        self.assertEqual(pci_address('bogus'),'')

    def test_slot_domain_functions(self):
        devices=[Path('0000:02:00.0'),Path('0000:02:00.1'),Path('0001:02:00.0')]
        self.assertEqual(slot_matches('00000000:02:00',devices),devices[:2])
        self.assertEqual(slot_matches('',devices),[])
        self.assertEqual(slot_matches('0000:03:00',devices),[])

    def test_monitor_name_difference_verified_by_edid(self):
        identity=edid();hex_lines='\n'.join('\t\t'+identity.hex()[i:i+32] for i in range(0,256,32))
        text='HDMI-0 connected 1920x1080+0+0\n\tEDID:\n'+hex_lines+'\n   1920x1080 60.00*+\n'
        outputs=xrandr_outputs(text)
        connector={'name':'card1-HDMI-A-1','gpu':'0000:01:00.0','status':'connected','edid':identity}
        self.assertEqual(match_monitor(connector,[connector],outputs)['mode'],'1920x1080 / 60.00 Hz')

    def test_monitor_collision_disconnected_invalid_rejected(self):
        identity=edid();one=dict(name='card1-DP-1',gpu='0000:01:00.0',status='connected',edid=identity)
        two=dict(one,name='card2-DP-1',gpu='0000:02:00.0')
        output=dict(name='DP-1',connected=True,edid=identity,mode='1920x1080 / 60 Hz')
        self.assertIsNone(match_monitor(one,[one,two],[output]))
        self.assertIsNone(match_monitor(dict(one,status='disconnected'),[one],[output]))
        self.assertIsNone(match_monitor(one,[one],[output,output]))
        self.assertIsNone(match_monitor(dict(one,edid=b'bad'),[one],[output]))
        self.assertIsNone(match_monitor(one,[one],[dict(output,edid=edid(2))]))

    def test_detect_virt_only_documented_none_exit(self):
        with patch('modules.inventory.shutil.which',return_value='/bin/tool'),patch('modules.inventory.run_capped',return_value=('failed',1,'none\n','')):
            self.assertEqual(run(['systemd-detect-virt'],allowed_exits=((1,'none'),)),'none\n')
            self.assertEqual(run(['other-command']),'')
        with patch('modules.inventory.shutil.which',return_value='/bin/tool'),patch('modules.inventory.run_capped',return_value=('failed',1,'kvm\n','')):
            self.assertEqual(run(['systemd-detect-virt'],allowed_exits=((1,'none'),)),'')

    def test_sensor_unique_paths(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as name:
            root=Path(name)
            for i in (0,1):
                device=root/f'nvme{i}';device.mkdir()
                sensor=root/f'hwmon{i}';sensor.mkdir();(sensor/'device').symlink_to(device)
            self.assertEqual(sensor_origin(root/'hwmon0'),str(root/'nvme0'))
            self.assertNotEqual(sensor_origin(root/'hwmon0'),sensor_origin(root/'hwmon1'))

    def test_bluez_connection_and_private_alias_separate(self):
        devices=parse_bluez({'/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF':{'org.bluez.Device1':dict(Adapter='/org/bluez/hci0',Address='AA:BB:CC:DD:EE:FF',Alias='Personal headset',Connected=True,Icon='audio-headset')}})
        self.assertTrue(devices[0]['connected'])
        self.assertNotIn('AA',devices[0]['key'])
        self.assertEqual(devices[0]['alias'],'Personal headset')
        self.assertEqual(parse_bluez({}),[])

    def test_wifi_signal_bitrates_and_no_bssid(self):
        metrics=wifi_metrics('Connected to AA:BB:CC:DD:EE:FF\nSSID: PrivateWifi\nsignal: -45 dBm\nrx bitrate: 866.7 MBit/s\ntx bitrate: 400.0 MBit/s\n')
        self.assertEqual(metrics['ssid'],'PrivateWifi')
        self.assertEqual(metrics['signal'],'-45 dBm')
        self.assertEqual(metrics['rx_bitrate'],'866.7 MBit/s')
        self.assertNotIn('AA:BB',str(metrics))
        self.assertEqual(wifi_metrics('Not connected.')['signal'],'@unknown')

    def test_bridge_does_not_prove_slot_occupancy(self):
        devices=[Path('0000:02:00.0'),Path('0000:02:00.1')]
        values={'0000:02:00.0':'0x060400','0000:02:00.1':'0x030000'}
        reader=lambda p:values[p.parent.name]
        self.assertEqual(slot_occupants('0000:02:00',devices,reader),[devices[1]])
        self.assertEqual(slot_occupants('0000:02:00',devices,lambda p:''),[])

    def test_export_redacts_names_and_events(self):
        private='AA:BB:CC:DD:EE:FF 192.168.1.2 2001:db8::1'
        s=dict(created='10.10.2026',sections={'usb':[row(private,private)]})
        events=[dict(time='10.10.2026 12:00:00',kind='connected',device=private,connector='dev_AA_BB_CC_DD_EE_FF',state=private)]
        text=report(s,lambda key:key,events)
        for value in ('AA:BB:CC:DD:EE:FF','192.168.1.2','2001:db8::1','dev_AA_BB_CC_DD_EE_FF'):self.assertNotIn(value,text)
        self.assertIn(private,report(s,lambda key:key,events,True))
        self.assertEqual(redact('0000:01:00.0'),'0000:01:00.0')

    def test_empty_bank_single_state(self):
        s=dict(created='10.10.2026',sections={'ram':[row('A1','','empty')]})
        text=report(s,lambda key:'Leer' if key=='occupancy_empty' else key)
        self.assertEqual(text.count('Leer'),1)
        self.assertNotIn('@unknown',text)

    def test_precise_network_and_bluetooth_events(self):
        for family in ('lan_carrier','display','bluez'):
            marker={('_bluez','ready'):('','ready')}
            before={**marker,(family,'device'):('Device','disconnected')}
            after={**marker,(family,'device'):('Device','connected')}
            self.assertEqual(differences(before,after)[0]['kind'],'connected')
            self.assertEqual(differences(after,before)[0]['kind'],'disconnected')
        self.assertEqual(differences({}, {('_bluez','ready'):('','ready'),('bluez','id'):('Audio','connected')}),[])

    def test_bluez_unavailable_not_device_removal(self):
        previous={('_bluez','ready'):('','ready'),('bluez','id'):('Audio','connected')}
        with patch('modules.inventory.bluez_devices',return_value=None):current=device_state(previous)
        self.assertEqual(current[('bluez','id')],previous[('bluez','id')])
        self.assertFalse(any(e['connector']=='id' for e in differences(previous,current)))

class ReviewRegressionTests(unittest.TestCase):
    def test_occupancy_retains_components(self):
        from modules.hardware_sources import occupancy_matches
        for selected in ('occupied','empty','unknown'):
            self.assertTrue(occupancy_matches({'occupancy':''},selected))
            self.assertTrue(occupancy_matches({'occupancy':selected},selected))
        self.assertFalse(occupancy_matches({'occupancy':'empty'},'occupied'))

    def test_carrier_independent_of_operstate(self):
        from modules.hardware_sources import lan_states
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            p=Path(directory);(p/'device').mkdir();(p/'operstate').write_text('down');(p/'carrier').write_text('1')
            self.assertEqual(lan_states(p),('down','connected'))
            (p/'carrier').write_text('0')
            self.assertEqual(lan_states(p),('down','disconnected'))
            (p/'carrier').unlink()
            self.assertEqual(lan_states(p),('down','unknown'))
            (p/'device').rmdir();(p/'carrier').write_text('1')
            self.assertEqual(lan_states(p),('down','unknown'))
        self.assertEqual(differences({('lan','eth0'):('eth0','down')},{('lan','eth0'):('eth0','up')})[0]['kind'],'operational_changed')

    def test_sensor_model_and_fallback(self):
        from modules.hardware_sources import sensor_identity
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            p=Path(directory);(p/'nvme0').mkdir();(p/'hwmon').mkdir();(p/'hwmon/device').symlink_to((p/'nvme0').resolve())
            (p/'nvme0/model').write_text('Example SSD')
            self.assertIn('nvme0 / Example SSD',sensor_identity(p/'hwmon'))
            self.assertIn(str((p/'nvme0').resolve()),sensor_identity(p/'hwmon'))

if __name__=='__main__':unittest.main()
