import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MarkdownContent({ children, className = "" }) {
  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {typeof children === "string" ? children : ""}
      </ReactMarkdown>
    </div>
  );
}
