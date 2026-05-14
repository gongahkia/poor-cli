export type DiffOp = 'equal' | 'insert' | 'delete';
export interface DiffSegment {
  op: DiffOp;
  text: string;
}

/// word-level diff using simple LCS-based algorithm
export function diffWords(oldText: string, newText: string): DiffSegment[] {
  const oldWords = tokenize(oldText);
  const newWords = tokenize(newText);
  const ops = myersDiff(oldWords, newWords);
  return mergeConsecutive(ops);
}

function tokenize(text: string): string[] {
  // split on word boundaries, keeping whitespace and punctuation as tokens
  return text.match(/\S+|\s+/g) || [];
}

/// Myers diff (simplified O(ND) for word arrays)
function myersDiff(a: string[], b: string[]): DiffSegment[] {
  const n = a.length;
  const m = b.length;
  if (n === 0 && m === 0) return [];
  if (n === 0) return b.map((w) => ({ op: 'insert' as DiffOp, text: w }));
  if (m === 0) return a.map((w) => ({ op: 'delete' as DiffOp, text: w }));
  // for very large inputs, fall back to simple line-by-line
  if (n + m > 10000) return fallbackDiff(a, b);
  const max = n + m;
  const vSize = 2 * max + 1;
  const v = new Int32Array(vSize).fill(-1);
  const trace: Int32Array[] = [];
  v[max + 1] = 0;
  for (let d = 0; d <= max; d++) {
    trace.push(v.slice());
    for (let k = -d; k <= d; k += 2) {
      let x: number;
      if (k === -d || (k !== d && v[max + k - 1] < v[max + k + 1])) {
        x = v[max + k + 1];
      } else {
        x = v[max + k - 1] + 1;
      }
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) { x++; y++; }
      v[max + k] = x;
      if (x >= n && y >= m) {
        return backtrack(trace, a, b, max);
      }
    }
  }
  return fallbackDiff(a, b);
}

function backtrack(trace: Int32Array[], a: string[], b: string[], offset: number): DiffSegment[] {
  let x = a.length;
  let y = b.length;
  const ops: DiffSegment[] = [];
  for (let d = trace.length - 1; d > 0; d--) {
    const v = trace[d - 1];
    const k = x - y;
    let prevK: number;
    if (k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1])) {
      prevK = k + 1;
    } else {
      prevK = k - 1;
    }
    const prevX = v[offset + prevK];
    const prevY = prevX - prevK;
    // diagonal (equal)
    while (x > prevX && y > prevY) {
      x--; y--;
      ops.unshift({ op: 'equal', text: a[x] });
    }
    if (x === prevX && y > prevY) {
      y--;
      ops.unshift({ op: 'insert', text: b[y] });
    } else if (y === prevY && x > prevX) {
      x--;
      ops.unshift({ op: 'delete', text: a[x] });
    }
  }
  // remaining diagonal at d=0
  while (x > 0 && y > 0) {
    x--; y--;
    ops.unshift({ op: 'equal', text: a[x] });
  }
  return ops;
}

function fallbackDiff(a: string[], b: string[]): DiffSegment[] {
  const result: DiffSegment[] = [];
  result.push(...a.map((w) => ({ op: 'delete' as DiffOp, text: w })));
  result.push(...b.map((w) => ({ op: 'insert' as DiffOp, text: w })));
  return result;
}

function mergeConsecutive(segments: DiffSegment[]): DiffSegment[] {
  if (segments.length === 0) return [];
  const merged: DiffSegment[] = [segments[0]];
  for (let i = 1; i < segments.length; i++) {
    const last = merged[merged.length - 1];
    if (last.op === segments[i].op) {
      last.text += segments[i].text;
    } else {
      merged.push({ ...segments[i] });
    }
  }
  return merged;
}
