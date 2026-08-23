import { useRef, useState, type ComponentPropsWithoutRef } from 'react';
import { Check, Copy } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

function CodeBlockWrapper({ children, ...props }: ComponentPropsWithoutRef<'pre'>) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  const handleCopy = () => {
    if (!preRef.current) return;
    const codeText = preRef.current.innerText || '';
    navigator.clipboard.writeText(codeText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="relative group/code my-2.5">
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded-lg transition-colors border border-slate-700 opacity-0 group-hover/code:opacity-100 focus:opacity-100 z-10"
        title="复制代码"
      >
        {copied ? <Check size={13} className="text-green-400" /> : <Copy size={13} />}
      </button>
      <pre ref={preRef} className="!bg-slate-900 !text-slate-100 p-4 rounded-xl shadow-inner border border-slate-800 overflow-x-auto text-xs" {...props}>
        {children}
      </pre>
    </div>
  );
}

type Props = {
  text: string;
};

export default function MarkdownMessage({ text }: Props) {
  return (
    <ReactMarkdown
      components={{
        pre({ children, ...props }) {
          return (
            <CodeBlockWrapper {...props}>
              {children}
            </CodeBlockWrapper>
          );
        },
        code({ className, children, ...props }) {
          const isInline = !className || !className.includes('language-');
          return isInline ? (
            <code className="font-mono bg-slate-200/60 px-1.5 py-0.5 rounded text-cyan-800 text-xs" {...props}>
              {children}
            </code>
          ) : (
            <code className={`${className} font-mono text-xs`} {...props}>
              {children}
            </code>
          );
        },
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
