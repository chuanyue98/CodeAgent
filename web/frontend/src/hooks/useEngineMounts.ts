import { useEffect, useState } from 'react';
import { fetchEngineMounts } from '../api/system';

/** Engine id -> the resource kinds its launcher attaches. */
export type EngineMountTable = Record<string, ReadonlySet<string>>;

/**
 * Which engines each kind of resource reaches. It is fixed by the launchers,
 * not by anything the user edits, so it is read once. `null` while loading and
 * if the request fails -- callers then show no per-engine marks rather than a
 * table that claims nothing mounts anywhere.
 */
export function useEngineMounts(): EngineMountTable | null {
  const [table, setTable] = useState<EngineMountTable | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEngineMounts()
      .then(engines => {
        if (cancelled || engines.length === 0) return;
        setTable(Object.fromEntries(engines.map(engine => [engine.id, new Set(engine.mounts)])));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return table;
}
