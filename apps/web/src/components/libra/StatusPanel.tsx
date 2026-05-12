"use client";

import { useCallback, useEffect, useState } from "react";

import { useDeviceStatus } from "@/hooks/useDeviceStatus";
import { fetchSystemStatus } from "@/lib/api";
import type { ServiceHealth, ServiceStatus } from "@/types/voice";

const POLL_INTERVAL_MS = 30_000;

interface BackendServices {
  openai: ServiceHealth;
  elevenlabs: ServiceHealth;
  database: ServiceHealth;
  redis: ServiceHealth;
}

const BACKEND_ROWS: { key: keyof BackendServices; label: string }[] = [
  { key: "openai", label: "OpenAI" },
  { key: "elevenlabs", label: "ElevenLabs" },
  { key: "database", label: "Database" },
  { key: "redis", label: "Redis" },
];

const STATUS_LABEL: Record<ServiceStatus, string> = {
  connected: "Connected",
  not_configured: "Not connected",
  error: "Not connected",
};

const DOT_CLASS: Record<ServiceStatus, string> = {
  connected: "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.55)]",
  not_configured: "bg-white/25",
  error: "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.55)]",
};

type Row = { label: string; health: ServiceHealth | undefined; text: string };

function Section({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="panel-title">{title}</span>
      <ul className="flex flex-col gap-2">
        {rows.map(({ label, health, text }) => {
          const status: ServiceStatus = health?.status ?? "error";
          return (
            <li
              key={label}
              className="flex items-center justify-between gap-3"
              title={health?.detail ?? undefined}
            >
              <span className="flex items-center gap-2.5">
                <span
                  aria-hidden
                  className={[
                    "block h-1.5 w-1.5 rounded-full transition-colors",
                    health ? DOT_CLASS[status] : "bg-white/15",
                  ].join(" ")}
                />
                <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-white">
                  {label}
                </span>
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/55">
                {text}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function StatusPanel() {
  const [services, setServices] = useState<BackendServices | null>(null);
  const [error, setError] = useState<string | null>(null);
  const devices = useDeviceStatus();

  const load = useCallback(async () => {
    try {
      const body = await fetchSystemStatus();
      setServices(body.services);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => window.clearInterval(t);
  }, [load]);

  const serviceRows: Row[] = BACKEND_ROWS.map(({ key, label }) => {
    const health = services?.[key];
    const status: ServiceStatus = health?.status ?? "error";
    const text = health ? STATUS_LABEL[status] : error ? "Not connected" : "—";
    return { label, health, text };
  });

  const deviceRows: Row[] = [
    {
      label: "Microphone",
      health: devices.microphone,
      text: STATUS_LABEL[devices.microphone.status],
    },
    {
      label: "Speaker",
      health: devices.speaker,
      text: STATUS_LABEL[devices.speaker.status],
    },
    {
      label: "Camera",
      health: devices.camera,
      text: STATUS_LABEL[devices.camera.status],
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <Section title="Services" rows={serviceRows} />
      <Section title="Devices" rows={deviceRows} />
      {error && !services ? (
        <p className="text-[10px] leading-snug text-white/35">
          Backend unreachable.
        </p>
      ) : null}
    </div>
  );
}
