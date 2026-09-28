export type FgOutletTelemetry = {
  channel: number;
  on: boolean;
  power_w?: number;
  energy_kwh?: number;
  temperature_c?: number;
  event_code?: string;
};

export type FgDevice = {
  mac: string;
  name?: string;
  room?: string;
  firmware?: string;
  connected: boolean;
  outlet_names?: string[];
  telemetry?: {
    outlets?: FgOutletTelemetry[];
    total_power_w?: number;
    total_energy_kwh?: number;
    max_temperature_c?: number | null;
  };
};

type DeviceListResponse = { devices?: FgDevice[] };

export function normalizeApiUrl(value: string): string {
  const raw = value.trim();
  if (!raw) throw new Error('FG Link API URL is required');
  const url = new URL(raw);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('FG Link API URL must use http or https');
  }
  if (url.protocol === 'http:' && !isPrivateOrLocalHost(url.hostname)) {
    throw new Error('Plain HTTP is allowed only for local/private/VPN FG Link endpoints');
  }
  url.pathname = url.pathname.replace(/\/+$/, '');
  url.search = '';
  url.hash = '';
  return url.toString().replace(/\/$/, '');
}

export function isPrivateOrLocalHost(input: string): boolean {
  const host = input.replace(/^\[/, '').replace(/\]$/, '').toLowerCase();
  if (host === 'localhost' || host.endsWith('.local')) return true;
  if (host === '::1' || host.startsWith('fc') || host.startsWith('fd') || host.startsWith('fe80:')) return true;

  const parts = host.split('.');
  if (parts.length !== 4 || parts.some((part) => !/^\d{1,3}$/.test(part))) return false;
  const nums = parts.map(Number);
  if (nums.some((value) => value < 0 || value > 255)) return false;
  if (nums[0] === 10 || nums[0] === 127) return true;
  if (nums[0] === 192 && nums[1] === 168) return true;
  if (nums[0] === 169 && nums[1] === 254) return true;
  if (nums[0] === 172 && nums[1] >= 16 && nums[1] <= 31) return true;
  if (nums[0] === 100 && nums[1] >= 64 && nums[1] <= 127) return true;
  return false;
}

export class FgLinkApiClient {
  readonly baseUrl: string;

  constructor(
    apiUrl: string,
    private readonly token: string,
    private readonly timeoutMs = 5000,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {
    this.baseUrl = normalizeApiUrl(apiUrl);
    if (!token.trim()) throw new Error('FG Link CONTROL token is required');
  }

  async listDevices(): Promise<FgDevice[]> {
    const body = await this.request<DeviceListResponse>('/api/v1/devices', { method: 'GET' });
    return (body.devices ?? []).filter((device) => /^[0-9A-Fa-f]{12}$/.test(device.mac ?? ''));
  }

  async setOutlet(mac: string, outlet: number, on: boolean): Promise<void> {
    const normalizedMac = mac.replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
    if (!/^[0-9A-F]{12}$/.test(normalizedMac)) throw new Error('Invalid FG Link MAC');
    if (!Number.isInteger(outlet) || outlet < 1 || outlet > 4) throw new Error('Outlet must be 1..4');
    await this.request(
      `/api/v1/devices/${normalizedMac}/outlets/${outlet}?state=${on ? 'on' : 'off'}`,
      { method: 'POST' },
    );
  }

  private async request<T = unknown>(path: string, init: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(this.baseUrl + path, {
        ...init,
        headers: {
          Authorization: `Bearer ${this.token.trim()}`,
          Accept: 'application/json',
          ...(init.headers ?? {}),
        },
        signal: controller.signal,
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(`FG Link API ${response.status}: ${detail || response.statusText}`);
      }
      const text = await response.text();
      return (text ? JSON.parse(text) : {}) as T;
    } finally {
      clearTimeout(timer);
    }
  }
}
