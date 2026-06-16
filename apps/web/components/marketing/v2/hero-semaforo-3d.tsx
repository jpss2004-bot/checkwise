"use client";

import { useEffect, useRef, type MutableRefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

/**
 * The hero's signature WebGL moment: the semáforo as a true-3D ring.
 *
 * The verde / ámbar / rojo arcs use the same 78 / 12 / 10 split as the
 * card's compliance donut, so the flat metric and the 3D object read as one
 * idea — el expediente, en dos dimensiones. A teal key light catches the
 * metallic arcs ("teal catches light"); the ring spins slowly and the whole
 * group tilts toward the pointer for a gyroscopic, depth-rich feel.
 *
 * Mounted only on desktop, lazily (next/dynamic, ssr:false) so three.js is
 * never in the initial bundle, and paused (frameloop "never") when the hero
 * scrolls offscreen. aria-hidden + pointer-events-none: pure atmosphere,
 * never content, so SEO and the card's interactions are untouched.
 */

const COLORS = { verde: "#09c1b0", ambar: "#f5a623", rojo: "#e5484d" } as const;
const TAU = Math.PI * 2;
const GAP = 0.018 * TAU; // breathing room between arc segments

type Pointer = { x: number; y: number };

function Arc({
  color,
  start,
  frac,
}: {
  color: string;
  start: number;
  frac: number;
}) {
  const sweep = frac * TAU - GAP;
  const seg = Math.max(10, Math.ceil(300 * frac));
  return (
    <mesh rotation={[0, 0, start * TAU + GAP / 2]}>
      <torusGeometry args={[1.72, 0.12, 28, seg, sweep]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={0.72}
        metalness={0.55}
        roughness={0.2}
        toneMapped={false}
      />
    </mesh>
  );
}

function Ring({ pointer }: { pointer: MutableRefObject<Pointer> }) {
  const outer = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Group>(null);

  useFrame((_, delta) => {
    const d = Math.min(delta, 0.05); // clamp after a stutter / tab refocus
    if (ring.current) ring.current.rotation.z += d * 0.16;
    const o = outer.current;
    if (o) {
      const tx = pointer.current.x * 0.45;
      const ty = -pointer.current.y * 0.3;
      o.rotation.y += (tx - o.rotation.y) * 0.05;
      o.rotation.x += (ty - o.rotation.x) * 0.05;
    }
  });

  return (
    <group ref={outer} position={[0, 0.1, 0]}>
      <group ref={ring} rotation={[0.42, 0, 2.2]}>
        <Arc color={COLORS.verde} start={0} frac={0.78} />
        <Arc color={COLORS.ambar} start={0.78} frac={0.12} />
        <Arc color={COLORS.rojo} start={0.9} frac={0.1} />
      </group>
    </group>
  );
}

export default function HeroSemaforo3D({ active }: { active: boolean }) {
  const pointer = useRef<Pointer>({ x: 0, y: 0 });

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      pointer.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.y = (e.clientY / window.innerHeight) * 2 - 1;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  return (
    <Canvas
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      dpr={[1, 1.6]}
      gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      camera={{ position: [0, 0, 5.3], fov: 40 }}
      frameloop={active ? "always" : "never"}
    >
      <ambientLight intensity={0.6} />
      <pointLight
        position={[3, 2.5, 4]}
        intensity={72}
        color="#1ad6c4"
        distance={30}
        decay={2}
      />
      <pointLight
        position={[-4, -2, 3]}
        intensity={34}
        color="#0aa7c4"
        distance={30}
        decay={2}
      />
      <directionalLight position={[-2, 4, 6]} intensity={1.3} />
      <Ring pointer={pointer} />
    </Canvas>
  );
}
