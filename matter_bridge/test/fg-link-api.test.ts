import { describe, expect, it, vi } from 'vitest';

import { FgLinkApiClient, isPrivateOrLocalHost, normalizeApiUrl } from '../src/fg-link-api.js';

describe('FG Link API endpoint policy', () => {
  it('accepts LAN, loopback, CGNAT and local hostnames', () => {
    expect(isPrivateOrLocalHost('192.168.1.10')).toBe(true);
    expect(isPrivateOrLocalHost('10.1.2.3')).toBe(true);
    expect(isPrivateOrLocalHost('172.20.1.1')).toBe(true);
    expect(isPrivateOrLocalHost('100.100.1.2')).toBe(true);
    expect(isPrivateOrLocalHost('localhost')).toBe(true);
    expect(isPrivateOrLocalHost('fg-link.local')).toBe(true);
  });

  it('rejects public plain HTTP but permits HTTPS', () => {
    expect(() => normalizeApiUrl('http://8.8.8.8:18086')).toThrow(/Plain HTTP/);
    expect(normalizeApiUrl('https://bridge.example.com')).toBe('https://bridge.example.com');
  });
});

describe('FG Link API client', () => {
  it('lists devices with the bearer token', async () => {
    const fakeFetch = vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer secret');
      return new Response(JSON.stringify({
        devices: [{
          mac: '2CE032C7102F',
          name: 'Lab Strip',
          room: 'Lab',
          connected: true,
          outlet_names: ['PC', 'Monitor', 'Lamp', 'Router'],
          telemetry: { outlets: [{ channel: 1, on: true }] }
        }]
      }), { status: 200 });
    }) as unknown as typeof fetch;

    const api = new FgLinkApiClient('http://192.168.1.20:18086', 'secret', 1000, fakeFetch);
    const devices = await api.listDevices();
    expect(devices).toHaveLength(1);
    expect(devices[0]?.outlet_names?.[0]).toBe('PC');
  });

  it('forwards a single outlet command and rejects invalid channels', async () => {
    const fakeFetch = vi.fn(async (input: string | URL | Request) => {
      expect(String(input)).toContain('/api/v1/devices/2CE032C7102F/outlets/4?state=off');
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;

    const api = new FgLinkApiClient('http://10.0.0.5:18086', 'secret', 1000, fakeFetch);
    await api.setOutlet('2C:E0:32:C7:10:2F', 4, false);
    expect(fakeFetch).toHaveBeenCalledTimes(1);
    await expect(api.setOutlet('2CE032C7102F', 5, true)).rejects.toThrow(/1\.\.4/);
  });
});
