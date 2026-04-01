"use client";

/**
 * SearchBar — address/zip code input with submit button.
 * Calls onSearch with the entered address when submitted.
 */
import { useState, FormEvent } from "react";

interface SearchBarProps {
  onSearch: (address: string) => void;
  isLoading: boolean;
}

export default function SearchBar({ onSearch, isLoading }: SearchBarProps) {
  const [address, setAddress] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (address.trim()) {
      onSearch(address.trim());
    }
  };

  const examples = ["Houston, TX 77002", "Miami, FL 33101", "Phoenix, AZ 85001"];

  return (
    <div className="w-full max-w-2xl">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="flex-1 relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg">
            📍
          </span>
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Enter address, city, or zip code..."
            className="w-full pl-10 pr-4 py-3 rounded-xl border border-gray-300 focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none text-gray-800 placeholder-gray-400 text-sm"
            disabled={isLoading}
          />
        </div>
        <button
          type="submit"
          disabled={isLoading || !address.trim()}
          className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-semibold rounded-xl transition-colors text-sm whitespace-nowrap"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              Analyzing...
            </span>
          ) : "Assess Risk"}
        </button>
      </form>

      {/* Example queries */}
      <div className="flex gap-2 mt-2 flex-wrap">
        <span className="text-xs text-gray-400">Try:</span>
        {examples.map((ex) => (
          <button
            key={ex}
            onClick={() => { setAddress(ex); onSearch(ex); }}
            className="text-xs text-blue-500 hover:text-blue-700 hover:underline"
            disabled={isLoading}
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}
