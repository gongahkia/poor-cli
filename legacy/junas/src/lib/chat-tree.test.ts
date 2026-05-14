import { describe, expect, it } from 'vitest';
import {
  getLinearHistory,
  getBranchSiblings,
  addChild,
  createTreeFromLinear,
  generateDotTree,
} from '@/lib/chat-tree';
import type { Message } from '@/types/chat';

function msg(id: string, role: 'user' | 'assistant', content: string, parentId?: string): Message {
  return { id, role, content, timestamp: new Date(), parentId } as Message;
}

describe('chat-tree', () => {
  describe('addChild', () => {
    it('adds child to empty parent', () => {
      const parent = msg('p1', 'user', 'hi');
      const child = msg('c1', 'assistant', 'hello');
      const map = { p1: parent };
      const result = addChild(map, 'p1', child);
      expect(result.c1.parentId).toBe('p1');
      expect(result.p1.childrenIds).toContain('c1');
    });
    it('appends multiple children', () => {
      const parent = msg('p1', 'user', 'hi');
      let map: Record<string, Message> = { p1: parent };
      map = addChild(map, 'p1', msg('c1', 'assistant', 'a'));
      map = addChild(map, 'p1', msg('c2', 'assistant', 'b'));
      expect(map.p1.childrenIds).toEqual(['c1', 'c2']);
    });
    it('handles missing parent gracefully', () => {
      const child = msg('c1', 'assistant', 'hello');
      const result = addChild({}, 'missing', child);
      expect(result.c1.parentId).toBe('missing');
    });
  });

  describe('getLinearHistory', () => {
    it('returns ordered history from root to leaf', () => {
      const m1 = msg('m1', 'user', 'first');
      const m2 = msg('m2', 'assistant', 'second', 'm1');
      const m3 = msg('m3', 'user', 'third', 'm2');
      const map = { m1, m2, m3 };
      const history = getLinearHistory(map, 'm3');
      expect(history.map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
    });
    it('returns single node for root', () => {
      const m1 = msg('m1', 'user', 'only');
      expect(getLinearHistory({ m1 }, 'm1')).toHaveLength(1);
    });
    it('returns empty for unknown leaf', () => {
      expect(getLinearHistory({}, 'unknown')).toEqual([]);
    });
  });

  describe('getBranchSiblings', () => {
    it('returns siblings including self', () => {
      let map: Record<string, Message> = { p: msg('p', 'user', 'root') };
      map = addChild(map, 'p', msg('c1', 'assistant', 'a'));
      map = addChild(map, 'p', msg('c2', 'assistant', 'b'));
      const siblings = getBranchSiblings(map, 'c1');
      expect(siblings).toContain('c1');
      expect(siblings).toContain('c2');
    });
    it('returns self for root node', () => {
      const map = { r: msg('r', 'user', 'root') };
      expect(getBranchSiblings(map, 'r')).toEqual(['r']);
    });
  });

  describe('createTreeFromLinear', () => {
    it('chains messages as linear tree', () => {
      const messages = [msg('a', 'user', '1'), msg('b', 'assistant', '2'), msg('c', 'user', '3')];
      const { nodeMap, leafId } = createTreeFromLinear(messages);
      expect(leafId).toBe('c');
      expect(nodeMap.a.childrenIds).toContain('b');
      expect(nodeMap.b.childrenIds).toContain('c');
      expect(nodeMap.c.childrenIds).toEqual([]);
    });
  });

  describe('generateDotTree', () => {
    it('produces valid dot syntax', () => {
      let map: Record<string, Message> = {};
      map = addChild(map, '', msg('u1', 'user', 'hello'));
      map = addChild(map, 'u1', msg('a1', 'assistant', 'hi'));
      const dot = generateDotTree(map, 'a1');
      expect(dot).toContain('digraph G');
      expect(dot).toContain('USER');
      expect(dot).toContain('JUNAS');
    });
  });
});
