import type { RecommendationResponse } from "@/lib/types";
import { LogoIcon, PinIcon, PlateIcon, UnpluggedIcon } from "./Icons";
import { ResultCard } from "./ResultCard";

export function Header() {
  return (
    <>
      <div className="rr-header">
        <div className="rr-brand">
          <span className="rr-logo"><LogoIcon /></span>
          Restaurant Recommender
        </div>
        <span className="rr-badge"><PinIcon /> Bangalore</span>
      </div>
      <div className="rr-hero">
        <h1>Find your next favourite meal</h1>
        <p className="rr-muted">
          Tell us where you are and what you&apos;re craving. We&apos;ll pick five places worth trying, and tell you why.
        </p>
      </div>
    </>
  );
}

export function Banner({ kind, children }: { kind: "info" | "warning" | "error"; children: React.ReactNode }) {
  return <div className={`rr-banner rr-banner-${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

export function Skeleton({ count = 5 }: { count?: number }) {
  return (
    <>
      <h2 className="rr-section-title">Picking your top 5…</h2>
      <p className="rr-summary rr-muted" role="status">Checking menus and ratings. This usually takes a few seconds.</p>
      <div className="rr-grid" aria-busy="true">
        {Array.from({ length: count }, (_, i) => (
          <div key={i} className="rr-card rr-sk" aria-hidden="true">
            <span className="rr-sk-bar" style={{ width: "70%", height: 20 }} />
            <span className="rr-sk-bar" style={{ width: "40%" }} />
            <span className="rr-sk-bar" style={{ width: "50%", height: 28, background: "#EEF2E9", borderRadius: 999 }} />
            <div className="rr-why" style={{ background: "#FBF6F0" }}>
              <span className="rr-sk-bar" style={{ width: "100%", marginBottom: 8 }} />
              <span className="rr-sk-bar" style={{ width: "85%" }} />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function EmptyPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rr-state rr-state-empty">
      <span className="rr-state-icon" style={{ background: "#EAF0E4" }}><PlateIcon /></span>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  );
}

export function WelcomeState() {
  return (
    <EmptyPanel title="Your table is waiting">
      Pick a neighbourhood and a craving above, then tap <strong style={{ color: "#2B2A28" }}>Find restaurants</strong>.
      Your top five picks will appear here.
    </EmptyPanel>
  );
}

export function BackendDown({ onRetry, retrying }: { onRetry: () => void; retrying: boolean }) {
  return (
    <>
      <div className="rr-state rr-state-error" role="alert">
        <span className="rr-state-icon" style={{ background: "#FBEAE2" }}><UnpluggedIcon /></span>
        <h2>We can&apos;t reach the kitchen right now</h2>
        <p>The server may still be starting up. Give it a moment, then try again.</p>
        {process.env.NODE_ENV === "development" && (
          <div className="rr-code">
            Running it locally? Start the backend with<code>uvicorn backend.api:app --port 8000</code>
          </div>
        )}
      </div>
      <button type="button" className="rr-primary" onClick={onRetry} disabled={retrying}>
        {retrying ? "Trying…" : "Try again"}
      </button>
    </>
  );
}

export function Results({ data, location }: { data: RecommendationResponse; location: string }) {
  const recs = data.recommendations;
  const notes = data.notes.map((note) => <Banner key={note} kind="info">{note}</Banner>);
  if (recs.length === 0) {
    return (
      <>
        {notes}
        <EmptyPanel title="No matches this time">Try a different budget or cuisine, or a lower minimum rating.</EmptyPanel>
      </>
    );
  }
  return (
    <section aria-label="Recommendations">
      <h2 className="rr-section-title">Your top {recs.length} in {location}</h2>
      {data.summary && <p className="rr-summary rr-muted">{data.summary}</p>}
      {data.degraded && (
        <Banner kind="warning">AI explanations are unavailable right now, so these are the top-rated matches.</Banner>
      )}
      {notes}
      <div className="rr-grid">
        {recs.map((item) => <ResultCard key={item.rank} item={item} showExplanation={!data.degraded} />)}
      </div>
      <p className="rr-footer">Ranked from {data.candidates_considered} matching restaurants</p>
    </section>
  );
}
