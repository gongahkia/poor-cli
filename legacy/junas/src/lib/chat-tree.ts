import { Message } from '@/types/chat';

function escapeDotLabelText(text: string): string {
  return text
    .replace(/\\/g, '\\\\')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '\\"')
    .replace(/\n/g, ' ');
}

export function getLinearHistory(nodeMap: Record<string, Message>, leafId: string): Message[] {
  const history: Message[] = [];
  let currentId: string | undefined = leafId;

  while (currentId && nodeMap[currentId]) {
    const node: Message = nodeMap[currentId];
    history.unshift(node);
    currentId = node.parentId;
  }

  return history;
}

export function getBranchSiblings(nodeMap: Record<string, Message>, nodeId: string): string[] {
  const node = nodeMap[nodeId];
  if (!node || !node.parentId) return [nodeId];

  const parent = nodeMap[node.parentId];
  return parent.childrenIds || [nodeId];
}

export function addChild(
  nodeMap: Record<string, Message>,
  parentId: string,
  child: Message
): Record<string, Message> {
  const newNodeMap = { ...nodeMap };

  // Add child
  newNodeMap[child.id] = { ...child, parentId };

  // Update parent
  if (newNodeMap[parentId]) {
    const parent = { ...newNodeMap[parentId] };
    parent.childrenIds = [...(parent.childrenIds || []), child.id];
    newNodeMap[parentId] = parent;
  }

  return newNodeMap;
}

export function createTreeFromLinear(messages: Message[]): {
  nodeMap: Record<string, Message>;
  leafId: string;
} {
  const nodeMap: Record<string, Message> = {};
  let prevId: string | undefined = undefined;
  let leafId = '';

  messages.forEach((msg, index) => {
    const node = { ...msg, parentId: prevId, childrenIds: [] as string[] };
    if (index < messages.length - 1) {
      node.childrenIds = [messages[index + 1].id];
    }
    nodeMap[msg.id] = node;
    prevId = msg.id;
    leafId = msg.id;
  });

  return { nodeMap, leafId };
}

export function generateDotTree(
  nodeMap: Record<string, Message>,
  currentLeafId: string | undefined,
  darkMode: boolean = false
): string {
  let dot = 'digraph G {\n';
  dot += '  rankdir=TB;\n';
  dot += '  bgcolor="transparent";\n';
  // Updated styles: fontname "Inter, sans-serif", shape "rect" (angular box)
  dot += `  node [fontname="Inter, sans-serif", fontsize=11, style="filled", shape="rect", fontcolor="${darkMode ? '#e5e5e5' : '#171717'}", fillcolor="${darkMode ? '#262626' : '#ffffff'}", penwidth=1, margin="0.2,0.1", color="${darkMode ? '#404040' : '#e5e5e5'}"];\n`;
  dot += `  edge [penwidth=1, arrowsize=0.7, color="${darkMode ? '#404040' : '#e5e5e5'}", fontname="Inter, sans-serif"];\n`;

  // Identify active path
  const activePath = new Set<string>();
  let curr = currentLeafId;
  while (curr && nodeMap[curr]) {
    activePath.add(curr);
    curr = nodeMap[curr].parentId;
  }

  // Sort nodes by timestamp to ensure deterministic graph (mostly)
  const sortedNodes = Object.values(nodeMap).sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  sortedNodes.forEach((node) => {
    const isActive = activePath.has(node.id);
    const isLeaf = currentLeafId === node.id;

    const roleLabel = node.role === 'user' ? 'USER' : 'JUNAS';
    let contentPreview = escapeDotLabelText(node.content.substring(0, 30));
    if (node.content.length > 30) contentPreview += '...';

    const label = `${roleLabel}\\n${contentPreview}`;

    const color = isActive ? (darkMode ? '#ffffff' : '#000000') : darkMode ? '#525252' : '#aaaaaa';
    const fill = isActive
      ? isLeaf
        ? darkMode
          ? '#14532d'
          : '#e6ffe6'
        : darkMode
          ? '#404040'
          : '#f5f5f5'
      : darkMode
        ? '#262626'
        : '#ffffff';
    const shape = node.role === 'user' ? 'box' : 'rect'; // rect with rounded style

    // Use 'class' attribute for styling hook (viz.js supports it)
    dot += `  "${node.id}" [label="${label}", shape=${shape}, color="${color}", fillcolor="${fill}", id="node_${node.id}", class="tree-node ${isActive ? 'active' : ''}"];\n`;

    if (node.parentId) {
      const edgeColor =
        isActive && activePath.has(node.parentId)
          ? darkMode
            ? '#ffffff'
            : '#000000'
          : darkMode
            ? '#525252'
            : '#cccccc';
      const penWidth = isActive && activePath.has(node.parentId) ? 2 : 1;
      dot += `  "${node.parentId}" -> "${node.id}" [color="${edgeColor}", penwidth=${penWidth}];\n`;
    }
  });

  dot += '}';
  return dot;
}
