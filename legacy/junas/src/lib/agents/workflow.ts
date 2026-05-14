export type StepStatus = 'pending' | 'running' | 'done' | 'error';
export interface WorkflowStep {
  id: string;
  label: string;
  status: StepStatus;
  result?: string;
  error?: string;
}
export interface DocumentInput {
  name: string;
  text: string;
}
export interface WorkflowPlan {
  id: string;
  title: string;
  documents: DocumentInput[];
  steps: WorkflowStep[];
  finalOutput?: string;
}

export type WorkflowType = 'compare' | 'batch-review' | 'summarize-all';

export function planWorkflow(
  type: WorkflowType,
  documents: DocumentInput[],
): WorkflowPlan {
  const id = `wf_${Date.now()}`;
  const steps: WorkflowStep[] = [];
  switch (type) {
    case 'compare':
      steps.push(
        { id: `${id}_analyze`, label: 'Analyze each document', status: 'pending' },
        { id: `${id}_extract`, label: 'Extract key terms from all', status: 'pending' },
        { id: `${id}_matrix`, label: 'Generate comparison matrix', status: 'pending' },
        { id: `${id}_summary`, label: 'Write comparison summary', status: 'pending' },
      );
      return { id, title: `Compare ${documents.length} documents`, documents, steps };
    case 'batch-review':
      documents.forEach((doc, i) => {
        steps.push({ id: `${id}_review_${i}`, label: `Review: ${doc.name}`, status: 'pending' });
      });
      steps.push({ id: `${id}_consolidate`, label: 'Consolidate findings', status: 'pending' });
      return { id, title: `Batch review ${documents.length} documents`, documents, steps };
    case 'summarize-all':
      documents.forEach((doc, i) => {
        steps.push({ id: `${id}_sum_${i}`, label: `Summarize: ${doc.name}`, status: 'pending' });
      });
      steps.push({ id: `${id}_mega`, label: 'Generate combined executive summary', status: 'pending' });
      return { id, title: `Summarize ${documents.length} documents`, documents, steps };
  }
}

export function buildStepPrompt(
  type: WorkflowType,
  step: WorkflowStep,
  documents: DocumentInput[],
  priorResults: string[],
): string {
  const docContext = documents.map((d, i) => `--- Document ${i + 1}: ${d.name} ---\n${d.text.slice(0, 3000)}`).join('\n\n');
  const priorContext = priorResults.length > 0
    ? `\n\nPrior analysis results:\n${priorResults.join('\n\n')}`
    : '';
  switch (type) {
    case 'compare':
      if (step.label.includes('Analyze')) {
        return `Analyze each of the following documents. For each, identify: parties, subject matter, key obligations, important dates.\n\n${docContext}`;
      }
      if (step.label.includes('Extract')) {
        return `Based on the analysis below, extract key terms from each document into a structured list. Focus on: obligations, payment terms, termination, liability caps, IP ownership.\n${priorContext}`;
      }
      if (step.label.includes('matrix')) {
        return `Create a comparison matrix (as a markdown table) showing how each document handles: parties, obligations, payment, termination, liability, IP, dispute resolution.\n${priorContext}`;
      }
      return `Write a concise executive summary comparing these documents. Highlight key differences and recommend areas of concern.\n${priorContext}`;
    case 'batch-review':
      if (step.label.includes('Review:')) {
        const docName = step.label.replace('Review: ', '');
        const doc = documents.find((d) => d.name === docName);
        return `Review the following document under Singapore law. Identify: key terms, obligations, risks, compliance issues, and recommendations.\n\n${doc?.text.slice(0, 5000) || ''}`;
      }
      return `Consolidate the following individual document reviews into a single findings report with prioritized action items.\n${priorContext}`;
    case 'summarize-all':
      if (step.label.includes('Summarize:')) {
        const docName = step.label.replace('Summarize: ', '');
        const doc = documents.find((d) => d.name === docName);
        return `Provide a concise legal summary of this document:\n\n${doc?.text.slice(0, 5000) || ''}`;
      }
      return `Combine the following document summaries into one executive summary. Highlight cross-document themes and key takeaways.\n${priorContext}`;
  }
}

export function updateStepStatus(
  plan: WorkflowPlan,
  stepId: string,
  status: StepStatus,
  result?: string,
  error?: string,
): WorkflowPlan {
  return {
    ...plan,
    steps: plan.steps.map((s) =>
      s.id === stepId ? { ...s, status, result, error } : s
    ),
  };
}
