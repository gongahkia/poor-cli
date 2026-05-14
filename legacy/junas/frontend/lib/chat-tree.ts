/**
 * Conversation tree utilities — supports branching conversations.
 * Each message has parentId/childrenIds forming a DAG.
 */
export type MessageRole = "user" | "assistant" | "system";

export interface TreeMessage {
  id: string;
  role: MessageRole;
  content: string;
  parentId?: string;
  childrenIds: string[];
  timestamp: number;
  tokenCount?: number;
  responseTimeMs?: number;
}

export type NodeMap = Record<string, TreeMessage>;

export function createId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Walk from leaf to root, return in chronological order. */
export function getLinearHistory(nodeMap: NodeMap, leafId: string): TreeMessage[] {
  const path: TreeMessage[] = [];
  let current: string | undefined = leafId;
  while (current && nodeMap[current]) {
    path.push(nodeMap[current]);
    current = nodeMap[current].parentId;
  }
  return path.reverse();
}

/** Get sibling message IDs (children of same parent). */
export function getBranchSiblings(nodeMap: NodeMap, nodeId: string): string[] {
  const node = nodeMap[nodeId];
  if (!node?.parentId) return [nodeId];
  const parent = nodeMap[node.parentId];
  return parent?.childrenIds ?? [nodeId];
}

/** Add a child message to the tree. Returns new nodeMap. */
export function addChild(nodeMap: NodeMap, parentId: string, child: TreeMessage): NodeMap {
  const newMap = { ...nodeMap };
  child.parentId = parentId;
  newMap[child.id] = child;
  if (newMap[parentId]) {
    newMap[parentId] = {
      ...newMap[parentId],
      childrenIds: [...newMap[parentId].childrenIds, child.id],
    };
  }
  return newMap;
}

/** Convert flat message array to tree (linear chain). */
export function createTreeFromLinear(messages: TreeMessage[]): { nodeMap: NodeMap; leafId: string } {
  const nodeMap: NodeMap = {};
  for (let i = 0; i < messages.length; i++) {
    const msg = { ...messages[i], childrenIds: [] as string[] };
    if (i > 0) {
      msg.parentId = messages[i - 1].id;
      nodeMap[messages[i - 1].id] = {
        ...nodeMap[messages[i - 1].id],
        childrenIds: [...nodeMap[messages[i - 1].id].childrenIds, msg.id],
      };
    }
    nodeMap[msg.id] = msg;
  }
  return { nodeMap, leafId: messages.length > 0 ? messages[messages.length - 1].id : "" };
}

/** Find all leaf nodes (nodes with no children). */
export function findLeaves(nodeMap: NodeMap): string[] {
  return Object.values(nodeMap).filter((n) => n.childrenIds.length === 0).map((n) => n.id);
}

/** Find root node (node with no parent). */
export function findRoot(nodeMap: NodeMap): string | undefined {
  return Object.values(nodeMap).find((n) => !n.parentId)?.id;
}

/** Get the set of node IDs on the active path from root to leaf. */
export function getActivePath(nodeMap: NodeMap, leafId: string): Set<string> {
  const path = new Set<string>();
  let current: string | undefined = leafId;
  while (current && nodeMap[current]) {
    path.add(current);
    current = nodeMap[current].parentId;
  }
  return path;
}

// --- git graph layout ---

export interface GraphNode {
  id: string;
  role: MessageRole;
  label: string;
  lane: number;
  row: number;
  isActive: boolean;
  isLeaf: boolean;
  childrenIds: string[];
  parentId?: string;
}

export interface GraphEdge {
  fromId: string;
  toId: string;
  fromLane: number;
  fromRow: number;
  toLane: number;
  toRow: number;
  isActive: boolean;
}

export interface GraphLayout {
  nodes: GraphNode[];
  edges: GraphEdge[];
  maxLane: number;
  maxRow: number;
}

/** Compute git-graph layout for the conversation tree. */
export function computeGitGraphLayout(nodeMap: NodeMap, currentLeafId: string): GraphLayout {
  const rootId = findRoot(nodeMap);
  if (!rootId) return { nodes: [], edges: [], maxLane: 0, maxRow: 0 };
  const activePath = getActivePath(nodeMap, currentLeafId);
  const leaves = new Set(findLeaves(nodeMap));
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const laneMap: Record<string, number> = {};
  let nextLane = 1;
  let rowCounter = 0;
  // DFS: active branch gets lane 0, others get incrementing lanes
  function dfs(nodeId: string, lane: number) {
    if (!nodeMap[nodeId] || laneMap[nodeId] !== undefined) return;
    const msg = nodeMap[nodeId];
    laneMap[nodeId] = lane;
    const row = rowCounter++;
    const label = msg.content.slice(0, 60).replace(/\n/g, " ");
    nodes.push({
      id: nodeId, role: msg.role, label, lane, row,
      isActive: activePath.has(nodeId),
      isLeaf: leaves.has(nodeId),
      childrenIds: msg.childrenIds,
      parentId: msg.parentId,
    });
    // sort children: active-path child first, then others
    const sorted = [...msg.childrenIds].sort((a, b) => {
      const aActive = activePath.has(a) ? 0 : 1;
      const bActive = activePath.has(b) ? 0 : 1;
      return aActive - bActive;
    });
    for (let i = 0; i < sorted.length; i++) {
      const childLane = i === 0 ? lane : nextLane++;
      dfs(sorted[i], childLane);
      const childNode = nodes.find((n) => n.id === sorted[i]);
      if (childNode) {
        edges.push({
          fromId: nodeId, toId: sorted[i],
          fromLane: lane, fromRow: row,
          toLane: childNode.lane, toRow: childNode.row,
          isActive: activePath.has(nodeId) && activePath.has(sorted[i]),
        });
      }
    }
  }
  dfs(rootId, 0);
  return { nodes, edges, maxLane: nextLane - 1, maxRow: rowCounter - 1 };
}
