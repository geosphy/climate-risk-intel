"use client";

/**
 * RiskReport — displays the AI-generated narrative risk assessment.
 * Shows a 3-paragraph narrative with copy-to-clipboard and share actions.
 */
import { useState } from "react";
import { Copy, Check, ExternalLink } from "lucide-react";
import { RiskReport as RiskReportType } from "@/types/risk";

interface RiskReportProps {
  report: RiskReportType;
}

export default function RiskReport({ report }: RiskReportProps) {
  const [copied, setCopied] = useState(false);

  if (!report.ai_narrative) return null;

  const paragraphs = report.ai_narrative.split("\n\n").filter(Boolean);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(report.ai_narrative);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable — silently ignore
    }
  };

  return (
    <div className="rounded-xl border border-blue-100 overflow-hidden shadow-sm">
      {/* Card header */}
      <div className="bg-gradient-to-r from-slate-700 to-blue-800 px-5 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base">🤖</span>
          <h3 className="text-white font-semibold text-sm">AI Risk Assessment</h3>
          <span className="text-xs text-blue-200 bg-white/10 px-2 py-0.5 rounded-full">
            Claude AI
          </span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-blue-200 hover:text-white transition-colors"
          title="Copy narrative to clipboard"
        >
          {copied ? (
            <>
              <Check size={13} />
              Copied
            </>
          ) : (
            <>
              <Copy size={13} />
              Copy
            </>
          )}
        </button>
      </div>

      {/* Narrative */}
      <div className="bg-gradient-to-br from-slate-50 to-blue-50 px-5 py-4 space-y-3.5">
        {paragraphs.map((para, i) => (
          <p key={i} className="text-sm text-gray-700 leading-relaxed">
            {para}
          </p>
        ))}
      </div>

      {/* Footer */}
      <div className="bg-white border-t border-blue-100 px-5 py-2.5 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          Generated {new Date(report.generated_at).toLocaleString()}
        </span>
        <a
          href="https://github.com/anthropics/claude-code"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-600 transition-colors"
        >
          Open Source
          <ExternalLink size={11} />
        </a>
      </div>
    </div>
  );
}
