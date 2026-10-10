import unittest
from unittest.mock import patch
from modules.ram_snapshot import merge_snapshot
from modules.device_details import current_state
from modules.inventory import report


def generation(time='10.10.2026 12:00:00',module='A',mode='ram_mode_admin',confirmed=True):
    identity='ram:'+module
    detail=dict(id=identity,family='ram',name='DIMM0',captured_at=time,query_mode=mode,capture_status='ram_capture_ok',fields=dict(model=module,serial='PRIVATE'))
    return dict(created=time,ram_capture=dict(confirmed=confirmed,captured_at=time,query_mode=mode,status='ram_capture_ok' if confirmed else 'ram_capture_unavailable'),sections={'ram':[dict(name='DIMM0',value=module,occupancy='occupied',device_id=identity,slot_id='slot0',personal=False)]},details={identity:detail})


class RamSnapshotTests(unittest.TestCase):
    def test_failed_or_restricted_refresh_preserves_original_time(self):
        old=generation()
        for incoming in (None,generation('10.10.2026 13:00:00',confirmed=False)):
            result=merge_snapshot(old,incoming)
            self.assertEqual(result['ram_capture']['captured_at'],old['ram_capture']['captured_at'])
            self.assertEqual(result['ram_capture']['status'],'ram_capture_old')
            self.assertEqual(result['details']['ram:A']['fields']['serial'],'PRIVATE')
            self.assertEqual(old['ram_capture']['status'],'ram_capture_ok')

    def test_successful_refresh_atomically_replaces_generation(self):
        old=generation();new=generation('10.10.2026 13:00:00','B','ram_mode_normal')
        result=merge_snapshot(old,new)
        self.assertNotIn('ram:A',result['details']);self.assertIn('ram:B',result['details'])
        self.assertEqual(result['ram_capture']['captured_at'],new['created'])
        self.assertEqual(result['ram_capture']['status'],'ram_capture_ok')
        self.assertEqual(old['sections']['ram'][0]['value'],'A')

    def test_confirmed_empty_retires_old_module(self):
        old=generation();new=generation('10.10.2026 13:00:00')
        new['details']={};new['sections']['ram'][0].update(occupancy='empty',value='')
        new['sections']['ram'][0].pop('device_id')
        result=merge_snapshot(old,new)
        self.assertEqual(result['sections']['ram'][0]['occupancy'],'empty')
        self.assertFalse(result['details'])

    def test_missing_previous_slot_is_restricted_not_removal(self):
        old=generation();old['sections']['ram'].append(dict(name='DIMM1',occupancy='empty',slot_id='slot1'))
        result=merge_snapshot(old,generation('10.10.2026 13:00:00','B'))
        self.assertEqual(result['ram_capture']['status'],'ram_capture_old')
        self.assertEqual(len(result['sections']['ram']),2)
        self.assertIn('ram:A',result['details'])

    def test_ram_current_state_does_not_query(self):
        with patch('modules.inventory.run',side_effect=AssertionError('unexpected hardware query')):
            self.assertIsNone(current_state(generation()['details']['ram:A']))

    def test_old_export_timestamp_status_and_serial_privacy(self):
        result=merge_snapshot(generation(),None)
        text=report(result,lambda key:key)
        self.assertIn('10.10.2026 12:00:00',text);self.assertIn('ram_capture_old',text);self.assertIn('ram_mode_admin',text)
        self.assertNotIn('PRIVATE',text)
        self.assertIn('PRIVATE',report(result,lambda key:key,personal=True))

    def test_no_initial_confirmation_fabricated(self):
        self.assertIsNone(merge_snapshot(None,None))
        result=merge_snapshot(None,generation(confirmed=False))
        self.assertFalse(result['ram_capture']['confirmed'])
        self.assertEqual(result['ram_capture']['status'],'ram_capture_unavailable')
