import React, { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';
import { MermaidDiagram } from './MermaidDiagram';

interface MarkdownRendererProps {
    content: string;
}

const MarkdownRenderer = memo(({ content }: MarkdownRendererProps) => {
    return (
        <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={{
                code: ({ node, className, children, ...props }: any) => {
                    const match = /language-(\w+)/.exec(className || '');
                    const inline = !match;
                    const language = match?.[1];

                    // Handle diagram code blocks - always use Mermaid
                    const diagramLanguages = ['mermaid', 'diagram', 'plantuml', 'd2', 'graphviz', 'dot'];
                    if (!inline && language && diagramLanguages.includes(language)) {
                        const chartCode = String(children).trim();
                        return <MermaidDiagram chart={chartCode} />;
                    }

                    return !inline && match ? (
                        <pre className="bg-muted p-3 rounded-md overflow-x-auto">
                            <code className={className} {...props}>
                                {children}
                            </code>
                        </pre>
                    ) : (
                        <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                            {children}
                        </code>
                    );
                },
                table: ({ children }) => (
                    <div className="overflow-x-auto">
                        <table className="min-w-full border-collapse border border-border">
                            {children}
                        </table>
                    </div>
                ),
                th: ({ children }) => (
                    <th className="border border-border px-3 py-2 bg-muted font-semibold text-left">
                        {children}
                    </th>
                ),
                td: ({ children }) => (
                    <td className="border border-border px-3 py-2">
                        {children}
                    </td>
                ),
            }}
        >
            {content}
        </ReactMarkdown>
    );
});

MarkdownRenderer.displayName = 'MarkdownRenderer';

export default MarkdownRenderer;
