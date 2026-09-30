import asyncio
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from direct_mttl_lab import DirectMttlLab, parse_getinfo
from app.direct_mttl import DirectMttlAdapter

MAC = '2CE032C7A520'
BOOT = f'up:bootinfo:lgutap;{MAC};{MAC};1.0.66-0.1.54;connect\r\n'


class DirectSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lab = DirectMttlLab('127.0.0.1', 0, MAC, 'lgutap', 5, '127.0.0.1', 0, True)
        self.lab.command_timeout = .06
        await self.lab.start()
        self.port = self.lab._server.sockets[0].getsockname()[1]
        self.admin_port = self.lab._admin_server.sockets[0].getsockname()[1]
        self.writers = []

    async def asyncTearDown(self):
        for writer in self.writers:
            writer.close()
            await writer.wait_closed()
        await self.lab.stop()
        await asyncio.sleep(.01)

    async def connect(self):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        self.writers.append(writer)
        writer.write(BOOT.encode())
        await writer.drain()
        self.assertEqual(await reader.readline(), b'up:getinfo:all\r\n')
        return reader, writer

    async def test_adapter_roundtrip_and_fresh_confirmation(self):
        reader, writer = await self.connect()
        self.lab.command_timeout = 1
        with patch.dict('os.environ', {'FGRCK_DIRECT_MTTL_ADMIN_PORT': str(self.admin_port),
                                      'FGRCK_DIRECT_MTTL_MACS': MAC}):
            adapter = DirectMttlAdapter()
            status = await asyncio.to_thread(adapter.status, MAC)
            self.assertTrue(status['connected'])
            task = asyncio.create_task(asyncio.to_thread(adapter.control, MAC, 1, 'on'))
            self.assertEqual(await reader.readline(), b'up:onoff:1:on\r\n')
            self.assertFalse(task.done())
            writer.write(b'up:onoff:1:on\r\n')
            await writer.drain()
            self.assertEqual((await task)['status'], 'confirmed')
            self.assertEqual(self.lab.devices[MAC].outlets[1]['relay'], 'on')

    async def test_live_nul_telemetry_confirms_command(self):
        reader, writer = await self.connect()
        self.lab.command_timeout = 1
        command = asyncio.create_task(self.lab.admin_command(f'on {MAC} 1'))
        self.assertEqual(await reader.readline(), b'up:onoff:1:on\r\n')
        frame = (Path(__file__).parent / 'fixtures/mttl_w01_live_getinfo.txt').read_bytes().strip()
        writer.write(b'\x00' + frame + b'\r\n\x00\n')
        await writer.drain()
        self.assertEqual((await command)['status'], 'confirmed')
        self.assertEqual(self.lab.devices[MAC].outlets[1]['energy_wh'], 1)
        self.assertEqual(self.lab.devices[MAC].outlets[4]['temperature_c'], 26)

    async def test_unix_socket_adapter(self):
        await self.connect()
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'admin.sock')
            server = await asyncio.start_unix_server(self.lab.handle_admin, path=path)
            try:
                with patch.dict('os.environ', {'FGRCK_DIRECT_MTTL_SOCKET': path}):
                    status = await asyncio.to_thread(DirectMttlAdapter().status, MAC)
                    self.assertTrue(status['connected'])
            finally:
                server.close()
                await server.wait_closed()

    async def test_timeout_does_not_confirm_cached_state(self):
        await self.connect()
        self.lab.devices[MAC].outlets[1] = {'channel': 1, 'relay': 'on'}
        result = await self.lab.admin_command(f'on {MAC} 1')
        self.assertEqual(result['status'], 'timeout')

    async def test_duplicate_session_and_offline(self):
        first_reader, _ = await self.connect()
        await self.connect()
        self.assertEqual(await asyncio.wait_for(first_reader.readline(), 1), b'')
        self.assertIn(MAC, self.lab.devices)
        self.writers[-1].close()
        for _ in range(20):
            if MAC not in self.lab.devices:
                break
            await asyncio.sleep(.01)
        self.assertNotIn(MAC, self.lab.devices)
        self.assertFalse((await self.lab.admin_command(f'on {MAC} 1'))['ok'])

    async def test_disconnect_fails_pending_command(self):
        reader, writer = await self.connect()
        task = asyncio.create_task(self.lab.admin_command(f'on {MAC} 1'))
        await reader.readline()
        writer.close()
        self.assertEqual((await task)['status'], 'failed')

    async def test_control_disabled_and_rate_limit(self):
        reader, writer = await self.connect()
        self.lab.allow_control = False
        self.assertFalse((await self.lab.admin_command(f'on {MAC} 1'))['ok'])
        self.lab.allow_control = True
        task = asyncio.create_task(self.lab.admin_command(f'on {MAC} 1'))
        await reader.readline()
        self.assertIn('rate limited', (await self.lab.admin_command(f'off {MAC} 2'))['error'])
        writer.write(b'up:event:onoff:1:on\r\n')
        await writer.drain()
        self.assertEqual((await task)['status'], 'confirmed')

    async def test_unknown_mac_rejected(self):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        self.writers.append(writer)
        writer.write(BOOT.replace(MAC, 'AABBCCDDEEFF').encode())
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readline(), 1), b'')
        self.assertFalse(self.lab.devices)

    async def test_multiple_registered_macs_and_persistent_allowlist(self):
        other = 'AABBCCDDEEFF'
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'allowed.json')
            self.lab.allowlist_file = path
            self.assertFalse((await self.lab.admin_command('allow invalid'))['ok'])
            self.assertFalse((await self.lab.admin_command('allowmany ' + other + ',invalid'))['ok'])
            self.assertEqual(self.lab.allowed_macs, {MAC})
            self.assertTrue((await self.lab.admin_command('allowmany ' + MAC + ',' + other))['ok'])
            await self.connect()
            reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
            self.writers.append(writer)
            writer.write(BOOT.replace(MAC, other).encode())
            await writer.drain()
            self.assertEqual(await reader.readline(), b'up:getinfo:all\r\n')
            self.assertEqual(set(self.lab.devices), {MAC, other})
            self.lab.command_timeout = 1
            task = asyncio.create_task(self.lab.admin_command(f'on {other} 4'))
            self.assertEqual(await reader.readline(), b'up:onoff:4:on\r\n')
            writer.write(b'up:onoff:4:on\r\n')
            await writer.drain()
            self.assertEqual((await task)['status'], 'confirmed')
            with patch.dict('os.environ', {'NEXVARY_MTTL_ALLOWED_MACS_FILE': path}):
                restarted = DirectMttlLab('127.0.0.1', 0, MAC, 'lgutap', 5, '127.0.0.1', 0, True)
                self.assertEqual(restarted.allowed_macs, {MAC, other})

    def test_public_admin_and_unlisted_control_rejected(self):
        with self.assertRaises(ValueError):
            DirectMttlLab('', 0, MAC, '', 5, '0.0.0.0', 0, True)
        with self.assertRaises(ValueError):
            DirectMttlLab('', 0, '', '', 5, '127.0.0.1', 0, True)

    def test_getinfo_trailing_delimiter(self):
        parsed = parse_getinfo('up:getinfo:1:0;off;3;on;on;1234;00000010;0;0;off;00;25:')
        self.assertEqual(parsed[0]['energy_wh'], 16)
        self.assertEqual(parsed[0]['power_w'], 1.234)
