"use client";

import { useCallback, useEffect, useState } from "react";

import {
  disconnectSpotify,
  fetchSpotifyStatus,
  spotifyConnectUrl,
  type SpotifyStatus,
} from "@/lib/api";

interface Props {
  /** Bumped from outside to force a status refresh (e.g. after OAuth bounce). */
  refreshKey?: number;
}

interface LastError {
  reason: string;
  ts: number;
}

function readLastError(): LastError | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("libra:spotify:last_error");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LastError;
    // Drop anything older than 1 hour – treat as stale.
    if (!parsed?.ts || Date.now() - parsed.ts > 60 * 60 * 1000) return null;
    return parsed;
  } catch {
    return null;
  }
}

function isPremiumOwnerError(reason: string): boolean {
  const r = reason.toLowerCase();
  return r.includes("premium") && r.includes("owner");
}

export function SpotifyPanel({ refreshKey = 0 }: Props) {
  const [status, setStatus] = useState<SpotifyStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastError, setLastError] = useState<LastError | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await fetchSpotifyStatus());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    setLastError(readLastError());
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const onConnect = useCallback(() => {
    // Hard navigation: top-level redirect to Spotify's OAuth flow.
    window.location.href = spotifyConnectUrl();
  }, []);

  const onClearLastError = useCallback(() => {
    try {
      window.localStorage.removeItem("libra:spotify:last_error");
    } catch {
      // ignore
    }
    setLastError(null);
  }, []);

  const onDisconnect = useCallback(async () => {
    setBusy(true);
    try {
      await disconnectSpotify();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [load]);

  return (
    <div className="flex flex-col gap-3">
      <span className="panel-title">Spotify</span>

      {status === null ? (
        <p className="text-[11px] leading-snug text-white/35">Checking…</p>
      ) : !status.configured ? (
        <p className="text-[11px] leading-snug text-white/55">
          Not configured on the server. Set{" "}
          <span className="font-mono text-white/80">SPOTIFY_CLIENT_ID</span>{" "}
          and{" "}
          <span className="font-mono text-white/80">SPOTIFY_CLIENT_SECRET</span>{" "}
          in <span className="font-mono text-white/80">.env</span> and restart
          the API.
        </p>
      ) : status.connected ? (
        <div className="flex flex-col gap-2.5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex flex-col">
              <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-white">
                {status.displayName ?? status.spotifyUserId ?? "Connected"}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-white/45">
                {status.product === "premium"
                  ? "Premium"
                  : status.product ?? "Connected"}
              </span>
            </div>
            <button
              type="button"
              onClick={onDisconnect}
              disabled={busy}
              className="rounded border border-white/15 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-white/70 transition hover:border-white/40 hover:text-white disabled:opacity-50"
            >
              Disconnect
            </button>
          </div>
          {status.product && status.product !== "premium" ? (
            <p className="text-[10.5px] leading-snug text-amber-200/70">
              Playback control requires Spotify Premium. Search will work, but
              play / pause / skip will be refused by Spotify.
            </p>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <button
            type="button"
            onClick={onConnect}
            className="rounded border border-white/15 px-3 py-2 font-mono text-[10.5px] uppercase tracking-[0.18em] text-white transition hover:border-white/45"
          >
            Connect Spotify
          </button>
          <p className="text-[10px] leading-snug text-white/40">
            Sends you through Spotify&apos;s standard OAuth flow. Connecting
            grants Libra permission to play / pause / skip and search.
          </p>

          {lastError ? (
            <div className="mt-1 flex flex-col gap-1 rounded border border-amber-300/25 bg-amber-300/5 px-2.5 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-amber-200/80">
                  Last attempt failed
                </span>
                <button
                  type="button"
                  onClick={onClearLastError}
                  className="font-mono text-[9px] uppercase tracking-[0.16em] text-amber-200/50 hover:text-amber-100"
                >
                  Dismiss
                </button>
              </div>
              {isPremiumOwnerError(lastError.reason) ? (
                <p className="text-[10.5px] leading-snug text-amber-100/85">
                  Spotify requires the developer-app owner&apos;s account to
                  have Premium. Spotify&apos;s cache can take a few hours to
                  refresh after a Premium upgrade — try again later. If
                  you&apos;re sure the right account is upgraded and it
                  still fails after 24h, recreate the app at
                  developer.spotify.com.
                </p>
              ) : (
                <p className="text-[10.5px] leading-snug text-amber-100/80">
                  {lastError.reason}
                </p>
              )}
            </div>
          ) : null}
        </div>
      )}

      {error ? (
        <p className="text-[10.5px] leading-snug text-red-300/80">{error}</p>
      ) : null}
    </div>
  );
}
