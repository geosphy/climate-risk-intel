"use client";

/**
 * RiskReport — displays the AI-generated narrative risk assessment.
 */
import { useState } from "react";
import { RiskReport as RiskReportType } from "@/types/risk";

interface RiskReportProps {
  report: RiskReportType;
}

export default function RiskReport({ report }: RiskReportProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(report.ai_narrative);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!report.ai_narrative) return null;

  const paragraphs = report.ai_narrative.split("\n\n").filter(Boolean);

  return (
    <div className="bg-gradient-to-br from-slate-50 to-blue-50 rounded-xl border border-blue-100 p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🤖</span>
          <h3 className="font-semibold text-gray-800 text-sm">
            AI Risk Assessment
          </h3>
          <span className="text-xs text-gray-400 bg-white px-2 py-0.5 rounded-full border">
            Claude AI
          </span>
        </div>
        <button
          onClick={handleCopy}
          className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
        >
          {copied ? "✓ Copied" : "Copy report"}
        </button>
      </div>

      {/* Narrative paragraphs */}
      <div className="space-y-3">
        {paragraphs.map((para, i) => (
          <p key={i} className="text-sm text-gray-700 leading-relaxed">
            {para}
          </p>
        ))}
      </div>

      {/* Timestamp */}
      <div className="mt-4 pt-3 border-t border-blue-100 text-xs text-gray-400">
        Generated: {new Date(report.generated_at).toLocaleString()} ·{" "}
        <a
          href="https://github.com/YOUR_USERNAME/climate-risk-intel"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
        >
          Open Source
        </a>
      </div>
    </div>
  );
}
