import { useState } from "react";
import { HeartPhoto } from "./Heart.jsx";

const MAX_LENGTH = 4000; // matches MAX_TEXT_LENGTH in backend/app/config.py
const SHOW_COUNT_FROM = 3500;
const TITLE = { boy: "His side", girl: "Her side" };

// What this person has said so far. The API only sends text once it can be shown.
function Record({ person, view }) {
  const answered = view.rounds.filter((round) => round.answers?.[person]);
  if (!view.statements) return null;
  return (
    <div className="record">
      <p className="bubble">{view.statements[person]}</p>
      {answered.map((round) => (
        <div key={round.number}>
          <p className="record__question">{round.questions[person]}</p>
          <p className="bubble">{round.answers[person]}</p>
        </div>
      ))}
    </div>
  );
}

// A line saying where this person is, for when there is nothing for them to type.
function statusLine(person, view, mine) {
  if (view.status === "awaiting_statements") {
    if (view.submitted[person]) return mine ? "Sealed. Waiting for the other side." : "Side sealed.";
    if (!view.seats_taken[person]) return mine ? null : "Hasn't joined yet.";
    return mine ? null : "Still writing…";
  }
  if (view.status === "awaiting_answers") {
    const round = view.rounds.at(-1);
    if (!round.questions[person]) return "No question this round.";
    if (round.answered.includes(person)) return mine ? "Sent. Waiting for the other answer." : "Answered.";
    return mine ? null : "Thinking about the question…";
  }
  return null;
}

export default function Side({ person, view, mine, outcome, onSubmit }) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  const isAnswering = view.status === "awaiting_answers";
  // Only the device that holds this seat can write here, and only when the lawyer wants it.
  const canWrite = mine && view.awaiting.includes(person);
  const status = canWrite ? null : statusLine(person, view, mine);
  const title = mine ? "Your side" : TITLE[person];

  async function handleSubmit(event) {
    event.preventDefault();
    setSending(true);
    setError(null);
    try {
      await onSubmit(draft.trim());
      setDraft("");
    } catch (failure) {
      setError(failure.message); // the draft stays, so nothing has to be retyped
    } finally {
      setSending(false);
    }
  }

  return (
    <section className={`side side--${person} ${mine ? "side--mine" : ""}`} aria-label={title}>
      <HeartPhoto person={person} outcome={outcome} />
      <div className="panel">
        <h2 className="panel__title">{title}</h2>
        <Record person={person} view={view} />
        {status && <p className="sealed">{status}</p>}
        {canWrite && (
          <form onSubmit={handleSubmit}>
            <textarea
              className="field"
              aria-label={isAnswering ? "Your answer" : "Your side of the story"}
              rows={5}
              maxLength={MAX_LENGTH}
              placeholder={
                isAnswering ? "Answer the lawyer's question." : "What happened, from where you're standing?"
              }
              value={draft}
              disabled={sending}
              onChange={(event) => setDraft(event.target.value)}
            />
            {draft.length >= SHOW_COUNT_FROM && (
              <p className="count">{draft.length} of {MAX_LENGTH} characters</p>
            )}
            {error && <p className="side-error" role="alert">{error}</p>}
            <button className="btn" type="submit" disabled={sending || !draft.trim()}>
              {isAnswering ? (sending ? "Sending…" : "Send my answer") : sending ? "Sealing…" : "Seal my side"}
            </button>
          </form>
        )}
      </div>
    </section>
  );
}
