import {
  bridgedNode,
  MatterbridgeDynamicPlatform,
  MatterbridgeEndpoint,
  onOffPlugInUnit,
  powerSource,
  type PlatformConfig,
  type PlatformMatterbridge,
} from 'matterbridge';
import { type AnsiLogger } from 'matterbridge/logger';
import { BridgedDeviceBasicInformation, OnOff } from 'matterbridge/matter/clusters';

import { FgLinkApiClient, type FgDevice } from './fg-link-api.js';

export type FgLinkMatterConfig = PlatformConfig & {
  apiUrl: string;
  token: string;
  pollIntervalSeconds?: number;
  exposeOfflineDevices?: boolean;
};

type EndpointRecord = {
  endpoint: MatterbridgeEndpoint;
  mac: string;
  outlet: number;
};

export default function initializePlugin(
  matterbridge: PlatformMatterbridge,
  log: AnsiLogger,
  config: FgLinkMatterConfig,
): FgLinkMatterBridgePlatform {
  return new FgLinkMatterBridgePlatform(matterbridge, log, config);
}

export class FgLinkMatterBridgePlatform extends MatterbridgeDynamicPlatform {
  private api: FgLinkApiClient | undefined;
  private refreshTimer: NodeJS.Timeout | undefined;
  private readonly endpoints = new Map<string, EndpointRecord>();
  private refreshRunning = false;

  constructor(
    matterbridge: PlatformMatterbridge,
    log: AnsiLogger,
    override config: FgLinkMatterConfig,
  ) {
    super(matterbridge, log, config);
    if (typeof this.verifyMatterbridgeVersion !== 'function' || !this.verifyMatterbridgeVersion('3.10.11')) {
      throw new Error('matterbridge-fg-link requires Matterbridge >= 3.10.11');
    }
  }

  override async onStart(reason?: string): Promise<void> {
    this.log.info(`Starting FG Link Matter Bridge: ${reason ?? 'normal start'}`);
    await this.ready;

    try {
      this.api = new FgLinkApiClient(this.config.apiUrl ?? '', this.config.token ?? '');
    } catch (error) {
      this.log.error(`FG Link Matter Bridge configuration error: ${messageOf(error)}`);
      return;
    }

    await this.refreshFromFgLink();

    const pollSeconds = clamp(Number(this.config.pollIntervalSeconds ?? 5), 2, 60);
    this.refreshTimer = setInterval(() => {
      void this.refreshFromFgLink();
    }, pollSeconds * 1000);
  }

  private async refreshFromFgLink(): Promise<void> {
    if (!this.api || this.refreshRunning) return;
    this.refreshRunning = true;
    try {
      const devices = await this.api.listDevices();
      const seen = new Set<string>();

      for (const device of devices) {
        if (!device.connected && this.config.exposeOfflineDevices === false) continue;
        for (let outlet = 1; outlet <= 4; outlet++) {
          const key = endpointKey(device.mac, outlet);
          seen.add(key);
          let record = this.endpoints.get(key);
          if (!record) {
            record = await this.createOutlet(device, outlet);
            this.endpoints.set(key, record);
          }
          await this.applyReportedState(record.endpoint, device, outlet);
        }
      }

      for (const [key, record] of this.endpoints) {
        if (!seen.has(key)) {
          await record.endpoint.setAttribute(
            BridgedDeviceBasicInformation.id,
            'reachable',
            false,
            record.endpoint.log,
          );
        }
      }
    } catch (error) {
      this.log.warn(`FG Link refresh failed: ${messageOf(error)}`);
      for (const record of this.endpoints.values()) {
        await record.endpoint.setAttribute(
          BridgedDeviceBasicInformation.id,
          'reachable',
          false,
          record.endpoint.log,
        ).catch(() => undefined);
      }
    } finally {
      this.refreshRunning = false;
    }
  }

  private async createOutlet(device: FgDevice, outlet: number): Promise<EndpointRecord> {
    if (!this.api) throw new Error('FG Link API is not configured');

    const mac = normalizeMac(device.mac);
    const deviceName = cleanName(device.name) || `MTTL-W01 ${mac}`;
    const outletLabel = cleanName(device.outlet_names?.[outlet - 1]) || `Outlet ${outlet}`;
    const matterName = shorten(`${deviceName} · ${outletLabel}`, 64);
    const serial = `${mac}-O${outlet}`;

    const endpoint = new MatterbridgeEndpoint(
      [onOffPlugInUnit, bridgedNode, powerSource],
      { id: `fg-${mac.toLowerCase()}-${outlet}` },
      this.config.debug,
    )
      .createDefaultIdentifyClusterServer()
      .createDefaultBridgedDeviceBasicInformationClusterServer(
        matterName,
        serial,
        0xfff1,
        'FG Machines',
        'FG Link / MTTL-W01',
      )
      .createDefaultOnOffClusterServer()
      .createDefaultPowerSourceWiredClusterServer()
      .addRequiredClusterServers();

    await this.registerDevice(endpoint);

    endpoint.addCommandHandler('on', async () => {
      await this.forwardMatterCommand(endpoint, mac, outlet, true);
    });
    endpoint.addCommandHandler('off', async () => {
      await this.forwardMatterCommand(endpoint, mac, outlet, false);
    });

    this.log.info(`Matter outlet registered: ${matterName} [${serial}]`);
    return { endpoint, mac, outlet };
  }

  private async forwardMatterCommand(
    endpoint: MatterbridgeEndpoint,
    mac: string,
    outlet: number,
    on: boolean,
  ): Promise<void> {
    if (!this.api) throw new Error('FG Link API is not configured');
    try {
      await this.api.setOutlet(mac, outlet, on);
      await endpoint.setAttribute(OnOff.id, 'onOff', on, endpoint.log);
      await endpoint.setAttribute(
        BridgedDeviceBasicInformation.id,
        'reachable',
        true,
        endpoint.log,
      );
      this.log.info(`Matter → FG Link: ${mac} outlet ${outlet} ${on ? 'ON' : 'OFF'}`);
    } catch (error) {
      this.log.error(`Matter command failed for ${mac}/${outlet}: ${messageOf(error)}`);
      await endpoint.setAttribute(
        BridgedDeviceBasicInformation.id,
        'reachable',
        false,
        endpoint.log,
      ).catch(() => undefined);
      throw error;
    }
  }

  private async applyReportedState(
    endpoint: MatterbridgeEndpoint,
    device: FgDevice,
    outlet: number,
  ): Promise<void> {
    await endpoint.setAttribute(
      BridgedDeviceBasicInformation.id,
      'reachable',
      Boolean(device.connected),
      endpoint.log,
    );

    const telemetry = device.telemetry?.outlets?.find((item) => Number(item.channel) === outlet);
    if (telemetry && typeof telemetry.on === 'boolean') {
      await endpoint.setAttribute(OnOff.id, 'onOff', telemetry.on, endpoint.log);
    }
  }

  override async onShutdown(reason?: string): Promise<void> {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
    this.refreshTimer = undefined;
    this.log.info(`Stopping FG Link Matter Bridge: ${reason ?? 'normal shutdown'}`);
    if (this.config.unregisterOnShutdown) await this.unregisterAllDevices();
    await super.onShutdown(reason);
  }
}

function endpointKey(mac: string, outlet: number): string {
  return `${normalizeMac(mac)}:${outlet}`;
}

function normalizeMac(value: string): string {
  const mac = String(value ?? '').replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
  if (!/^[0-9A-F]{12}$/.test(mac)) throw new Error(`Invalid MAC: ${value}`);
  return mac;
}

function cleanName(value: string | undefined): string {
  return String(value ?? '').trim().replace(/[\r\n\t]+/g, ' ');
}

function shorten(value: string, max: number): string {
  return value.length <= max ? value : value.slice(0, max).trim();
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.round(value)));
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
