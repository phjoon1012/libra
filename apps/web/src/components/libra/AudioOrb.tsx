"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { MutableRefObject } from "react";
import * as THREE from "three";

import type { LevelListener } from "@/lib/voice/types";
import type { ConnectionState } from "@/types/voice";

interface Props {
  state: ConnectionState;
  subscribeLevel: (listener: LevelListener) => () => void;
}

interface SceneProps {
  levelRef: MutableRefObject<number>;
  stateRef: MutableRefObject<ConnectionState>;
}

/**
 * Wireframe icosahedron + vertex "node" points.
 * Scale reacts to a syllable-accent envelope (fast level minus slow
 * baseline) so vocal stresses pulse the sphere instead of steady tones.
 */
function GraphSphere({ levelRef, stateRef }: SceneProps) {
  const group = useRef<THREE.Group>(null);

  const geometry = useMemo(() => new THREE.IcosahedronGeometry(1, 3), []);
  const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 1), [geometry]);

  const fast = useRef(0);
  const slow = useRef(0);
  const accent = useRef(0);
  const time = useRef(0);

  useFrame((_, delta) => {
    const g = group.current;
    if (!g) return;

    time.current += delta;

    // Envelope: fast tracks instant loudness, slow tracks baseline.
    // Accent = fast - slow; spikes on stressed syllables, dies on holds.
    const target = levelRef.current;
    fast.current += (target - fast.current) * 0.7;
    slow.current += (target - slow.current) * 0.025;
    const rawAccent = Math.max(0, fast.current - slow.current * 0.45);
    accent.current += (rawAccent - accent.current) * 0.55;

    const s = stateRef.current;
    const ambient =
      s === "thinking"
        ? 0.05 + 0.03 * Math.sin(time.current * 2.4)
        : s === "listening"
          ? 0.03 + 0.015 * Math.sin(time.current * 1.4)
          : s === "connecting"
            ? 0.04 + 0.025 * Math.sin(time.current * 2.0)
            : 0;

    const energy = Math.min(1.8, accent.current * 3.2 + ambient);
    const scale = 0.92 + energy * 0.65;
    g.scale.setScalar(scale);

    g.rotation.y += delta * 0.18;
    g.rotation.x = Math.sin(time.current * 0.3) * 0.12;
  });

  return (
    <group ref={group}>
      <points geometry={geometry}>
        <pointsMaterial
          color="#ffffff"
          size={0.05}
          sizeAttenuation
          transparent
          opacity={0.95}
          depthWrite={false}
        />
      </points>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color="#ffffff" transparent opacity={0.18} />
      </lineSegments>
    </group>
  );
}

export function AudioOrb({ state, subscribeLevel }: Props) {
  const levelRef = useRef(0);
  const stateRef = useRef<ConnectionState>(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    return subscribeLevel((level) => {
      levelRef.current = level;
    });
  }, [subscribeLevel]);

  const dimmed = state === "disconnected" || state === "error";

  return (
    <div
      className="relative h-[380px] w-[380px]"
      style={{
        opacity: dimmed ? 0.35 : 1,
        transition: "opacity 400ms ease",
      }}
      aria-hidden
    >
      <Canvas
        camera={{ position: [0, 0, 3.2], fov: 42 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      >
        <GraphSphere levelRef={levelRef} stateRef={stateRef} />
      </Canvas>
    </div>
  );
}
