"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createMemoryFact,
  deleteMemoryFact,
  listMemoryFacts,
  searchMemoryFacts,
} from "@/lib/api";
import type { MemoryFact } from "@/types/voice";

interface Props {
  /** Bumps when the parent wants the panel to refetch (e.g. after disconnect). */
  refreshKey?: number;
}

const PAGE_SIZE = 50;

function formatAge(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export function MemoryPanel({ refreshKey = 0 }: Props) {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<MemoryFact[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [newFact, setNewFact] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await listMemoryFacts({ limit: PAGE_SIZE });
      setFacts(body.facts);
      setTotal(body.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload, refreshKey]);

  const runSearch = useCallback(async () => {
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const results = await searchMemoryFacts(query.trim(), 10);
      setSearchResults(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteMemoryFact(id);
        setFacts((prev) => prev.filter((f) => f.id !== id));
        setSearchResults((prev) => prev?.filter((f) => f.id !== id) ?? null);
        setTotal((n) => Math.max(0, n - 1));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [],
  );

  const handleAdd = useCallback(async () => {
    const content = newFact.trim();
    if (!content) return;
    try {
      await createMemoryFact(content, 3);
      setNewFact("");
      setAdding(false);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [newFact, reload]);

  const visible = useMemo(
    () => searchResults ?? facts,
    [searchResults, facts],
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="panel-title">Memory</span>
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-white/40">
          {searchResults ? `${searchResults.length} match` : `${total} total`}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={query}
          placeholder="Search memories…"
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void runSearch();
            if (e.key === "Escape") {
              setQuery("");
              setSearchResults(null);
            }
          }}
          className="flex-1 rounded-md border border-white/10 bg-transparent px-2.5 py-1.5 text-[12px] text-white outline-none transition focus:border-white/40"
        />
        {searchResults ? (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setSearchResults(null);
            }}
            className="rounded border border-white/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.22em] text-white/55 transition hover:border-white/30 hover:text-white"
          >
            Clear
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void runSearch()}
            disabled={!query.trim()}
            className="rounded border border-white/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.22em] text-white/55 transition hover:border-white/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Find
          </button>
        )}
      </div>

      {error ? (
        <p className="rounded border border-white/15 px-2.5 py-1.5 text-[10px] leading-snug text-white/55">
          {error}
        </p>
      ) : null}

      <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {visible.length === 0 && !loading ? (
          <li className="rounded border border-dashed border-white/10 px-3 py-4 text-center text-[11px] leading-snug text-white/40">
            {searchResults
              ? "No matches. Try different words."
              : "No memories yet. They appear after a conversation ends."}
          </li>
        ) : null}
        {visible.map((fact) => (
          <li
            key={fact.id}
            className="group flex flex-col gap-1.5 rounded border border-white/[0.07] bg-white/[0.015] px-2.5 py-2 transition hover:border-white/15"
          >
            <p className="text-[12px] leading-snug text-white/85">
              {fact.content}
            </p>
            <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.22em] text-white/35">
              <span>
                w{fact.importance} · {formatAge(fact.createdAt)}
                {fact.score != null ? ` · d=${fact.score.toFixed(3)}` : ""}
              </span>
              <button
                type="button"
                onClick={() => void handleDelete(fact.id)}
                className="opacity-0 transition group-hover:opacity-100 hover:text-white"
                aria-label="Forget this memory"
              >
                forget
              </button>
            </div>
          </li>
        ))}
      </ul>

      {adding ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={newFact}
            onChange={(e) => setNewFact(e.target.value)}
            rows={2}
            placeholder="User prefers…"
            className="resize-none rounded-md border border-white/10 bg-transparent px-2.5 py-1.5 text-[12px] text-white outline-none transition focus:border-white/40"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setAdding(false);
                setNewFact("");
              }}
              className="rounded border border-white/10 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.22em] text-white/55 transition hover:border-white/30 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleAdd()}
              disabled={!newFact.trim()}
              className="rounded border border-white/30 bg-white/5 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.22em] text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="rounded border border-dashed border-white/10 px-2 py-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-white/45 transition hover:border-white/25 hover:text-white"
        >
          + Add a memory manually
        </button>
      )}
    </div>
  );
}
