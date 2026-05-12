"use client";

import { Button } from "@/components/ui/Button";
import type { ConnectionState } from "@/types/voice";

interface Props {
  state: ConnectionState;
  muted: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onToggleMute: () => void;
  onInterrupt: () => void;
}

export function ControlBar({
  state,
  muted,
  onConnect,
  onDisconnect,
  onToggleMute,
  onInterrupt,
}: Props) {
  const isConnected = state !== "disconnected" && state !== "error";
  const isBusy = state === "connecting";

  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {isConnected ? (
        <Button variant="secondary" onClick={onDisconnect}>
          Disconnect
        </Button>
      ) : (
        <Button variant="primary" onClick={onConnect} disabled={isBusy}>
          {isBusy ? "Connecting" : "Connect"}
        </Button>
      )}
      <Button variant="secondary" onClick={onToggleMute} disabled={!isConnected}>
        {muted ? "Unmute" : "Mute"}
      </Button>
      <Button variant="ghost" onClick={onInterrupt} disabled={state !== "speaking"}>
        Interrupt
      </Button>
    </div>
  );
}
