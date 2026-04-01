"use client";

/**
 * SearchBar — address / zip code input with 300 ms debounce.
 * Calls onSearch after the user stops typing or presses Enter / button.
 */
import { useState, useEffect, useRef, FormEvent } from "react";

interface SearchBarProps {
  onSearch: (address: string) => void;
  isLoading: boolean;
}

const EXAMPLES = ["Houston, TX 77002", "Miami, FL 33101", "Phoenix, AZ 85001"];

// Spinner SVG — avoids lucide-react import so this file has zero extra deps
function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

export default function SearchBar({ onSearch, isLoading }: SearchBarProps) {
  const [address, setAddress] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up the timer when the component unmounts.
  useEffect(() => () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, []);

  /** Fire onSearch, with an optional 300 ms delay for type-ahead. */
  const fire = (value: string, immediate = false) => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const delay = immediate ? 0 : 300;
    debounceRef.current = setTimeout(() => onSearch(trimmed), delay);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    fire(address, true);          // explicit submit → no delay
  };

  const handleExample = (ex: string) => {
    setAddress(ex);
    fire(ex, true);
  };

  return (
    <div className="w-full max-w-2xl">
      <form onSubmit={handleSubmit} className="flex gap-2">
        {/* Input */}
        <div className="flex-1 relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/50 pointer-events-none select-none">
            📍
          </span>
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Enter address, city, or zip code…"
            aria-label="Address or zip code"
            autoComplete="off"
            disabled={isLoading}
            className="
              w-full pl-10 pr-4 py-3 rounded-xl text-sm outline-none transition-all duration-200
              border border-white/20 bg-white/10 text-white placeholder-white/40
              focus:bg-white focus:border-blue-400 focus:ring-2 focus:ring-blue-300/50
              focus:text-gray-800 focus:placeholder-gray-400
              disabled:opacity-60
            "
          />
        </div>

        {/* Submit button */}
        <button
          type="submit"
          disabled={isLoading || !address.trim()}
          className="
            px-6 py-3 rounded-xl font-semibold text-sm whitespace-nowrap
            flex items-center gap-2 transition-colors
            bg-blue-500 hover:bg-blue-400 active:bg-blue-600 text-white
            disabled:opacity-40 disabled:cursor-not-allowed
          "
        >
          {isLoading ? (
            <>
              <Spinner />
              Analyzing…
            </>
          ) : (
            "Assess Risk"
          )}
        </button>
      </form>

      {/* Quick-fill examples */}
      <div className="flex items-center gap-2 mt-2 flex-wrap">
        <span className="text-xs text-white/40">Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => handleExample(ex)}
            disabled={isLoading}
            className="text-xs text-blue-300 hover:text-white hover:underline disabled:opacity-40 transition-colors"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}
