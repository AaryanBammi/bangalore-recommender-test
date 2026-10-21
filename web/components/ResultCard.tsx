import type { RecommendationItem } from "@/lib/types";
import { PinIcon, StarIcon } from "./Icons";

export function titleCase(text: string): string {
  return text.replace(/\b\w/g, (c) => c.toUpperCase());
}

// Same bands as the backend budget filter: low ≤ 300, medium 301–700, high > 700.
export function priceLevel(cost: number): number {
  return cost <= 300 ? 1 : cost <= 700 ? 2 : 3;
}

export function ResultCard({ item, showExplanation }: { item: RecommendationItem; showExplanation: boolean }) {
  const level = item.cost_for_two === null ? 0 : priceLevel(item.cost_for_two);
  return (
    <article className="rr-card">
      <div className="rr-card-head">
        <span className="rr-rank">{item.rank}</span>
        <div>
          <h3 className="rr-name">{item.name}</h3>
          <span className="rr-loc"><PinIcon /> {item.location}</span>
        </div>
      </div>
      <div className="rr-tags">
        {item.cuisines.map((c) => <span key={c} className="rr-tag">{titleCase(c)}</span>)}
      </div>
      <div className="rr-meta">
        {item.rating !== null
          ? <span className="rr-rating"><StarIcon /> {item.rating.toFixed(1)}</span>
          : <span className="rr-rating rr-unrated">Unrated</span>}
        {item.cost_for_two !== null ? (
          <>
            <span className="rr-price" aria-hidden="true">{"₹".repeat(level)}<span>{"₹".repeat(3 - level)}</span></span>
            <span>₹{item.cost_for_two.toLocaleString("en-IN")} for two</span>
          </>
        ) : <span>Cost N/A</span>}
      </div>
      {showExplanation && item.explanation && (
        <div className="rr-why">
          <span className="rr-why-label">Why we picked this</span>
          <p>{item.explanation}</p>
        </div>
      )}
    </article>
  );
}
