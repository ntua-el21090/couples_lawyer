import { useState } from "react";
import { HeartPhoto } from "./Heart.jsx";
import { createAndOpen } from "./routes.js";

export default function Home({ onUnauthorized }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await createAndOpen();
    } catch (failure) {
      if (failure.status === 401) onUnauthorized();
      setError(failure.message);
      setBusy(false);
    }
  }

  return (
    <main className="court">
      <section className="side side--boy">
        <HeartPhoto person="boy" />
      </section>
      <section className="side side--girl">
        <HeartPhoto person="girl" />
      </section>
      <section className="bench" aria-label="The lawyer">
        <h1 className="bench__title">Love on Trial</h1>
        <div className="bench__body bench__body--center">
          <p className="bench__lead">
            Start a case, send the link to your other half, and each write your side on your own phone.
          </p>
          {error && <p className="bench__error" role="alert">{error}</p>}
          <button className="btn btn--light" onClick={start} disabled={busy}>
            {busy ? "Opening…" : "Start a case"}
          </button>
        </div>
        <footer className="bench__footer">
          <p className="disclaimer">Just for fun. Not legal advice or therapy.</p>
        </footer>
      </section>
    </main>
  );
}
