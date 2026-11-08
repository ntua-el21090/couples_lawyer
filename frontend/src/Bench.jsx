import { useState } from "react";
import { Heart } from "./Heart.jsx";

const PRONOUN = { boy: "him", girl: "her" };
const SUBJECT = { boy: "He's", girl: "She's" };
const PEOPLE = ["boy", "girl"];

// From this device's point of view, so "you" is whoever is holding it.
function waitingText(awaiting, me) {
  if (awaiting.length === 0) return "";
  const names = awaiting.map((person) => (person === me ? "you" : PRONOUN[person]));
  return `Waiting for ${names.join(" and ")}.`;
}

function SeatPicker({ view, onClaim }) {
  const [claiming, setClaiming] = useState(false);
  const [error, setError] = useState(null);

  async function claim(person) {
    setClaiming(true);
    setError(null);
    try {
      await onClaim(person);
    } catch (failure) {
      setError(failure.message);
      setClaiming(false);
    }
  }

  return (
    <div className="bench__body bench__body--center">
      <p className="bench__lead">Who's holding this phone?</p>
      <div className="seats">
        {PEOPLE.map((person) => (
          <button
            key={person}
            className="btn btn--light"
            disabled={claiming || view.seats_taken[person]}
            onClick={() => claim(person)}
          >
            {view.seats_taken[person] ? `${SUBJECT[person]} already here` : `I'm ${PRONOUN[person]}`}
          </button>
        ))}
      </div>
      {error && <p className="bench__error" role="alert">{error}</p>}
    </div>
  );
}

function Invite({ other, url }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Copying can be blocked. The link above stays selectable.
    }
  }

  return (
    <div className="invite">
      <p>Send this link to {PRONOUN[other]}.</p>
      <input
        className="invite__link"
        readOnly
        value={url}
        aria-label="Link to this case"
        onFocus={(event) => event.target.select()}
      />
      <button className="btn btn--light" onClick={copy}>
        {copied ? "Copied" : "Copy link"}
      </button>
    </div>
  );
}

function Questions({ view, mySeat }) {
  const round = view.rounds.at(-1);
  return (
    <div className="bench__body">
      <p className="bench__round">Question {view.current_round} of {view.max_rounds}</p>
      {PEOPLE.filter((person) => round.questions[person]).map((person) => (
        <div key={person} className={`question question--${person}`}>
          <p className="question__for">For {person === mySeat ? "you" : PRONOUN[person]}</p>
          <p>{round.questions[person]}</p>
        </div>
      ))}
      <p className="bench__hint">{waitingText(view.awaiting, mySeat)}</p>
    </div>
  );
}

function Verdict({ decision }) {
  if (decision.verdict === "safety_concern") {
    return (
      <div className="bench__body">
        <h3 className="safety__title">This is bigger than an argument</h3>
        <p>{decision.reasoning}</p>
        <p>{decision.advice}</p>
      </div>
    );
  }
  return (
    <div className="bench__body">
      <div className="candy">
        <Heart className="candy__heart" />
        <p className="candy__text">{decision.verdict === "boy" ? "He's right" : "She's right"}</p>
      </div>
      <h3 className="bench__heading">Why</h3>
      <p>{decision.reasoning}</p>
      <h3 className="bench__heading">What to do now</h3>
      <p>{decision.advice}</p>
    </div>
  );
}

function Body({ view, mySeat, thinking, inviteUrl, onClaim, onRetry }) {
  const freeSeat = PEOPLE.some((person) => !view.seats_taken[person]);
  const other = mySeat === "boy" ? "girl" : "boy";

  if (!mySeat && view.status === "awaiting_statements" && freeSeat) {
    return <SeatPicker view={view} onClaim={onClaim} />;
  }
  if (thinking) {
    return (
      <div className="bench__body bench__body--center">
        <Heart className="beat" />
        <p>Reading the evidence…</p>
      </div>
    );
  }
  if (view.status === "lawyer_failed") {
    return (
      <div className="bench__body bench__body--center">
        <p>{view.error}</p>
        <p className="bench__hint">Everything you wrote is safe.</p>
        {mySeat && <button className="btn btn--light" onClick={onRetry}>Try again</button>}
      </div>
    );
  }
  if (view.status === "awaiting_answers") return <Questions view={view} mySeat={mySeat} />;
  if (view.decision) return <Verdict decision={view.decision} />;

  return (
    <div className="bench__body">
      <p className="bench__lead">
        Tell me what happened, each on your own phone. I won't read a word until I have both sides.
      </p>
      {mySeat && !view.seats_taken[other] && <Invite other={other} url={inviteUrl} />}
      <p className="bench__hint">{waitingText(view.awaiting, mySeat)}</p>
    </div>
  );
}

export default function Bench({ view, mySeat, thinking, error, offline, inviteUrl, onClaim, onRetry, onStartOver }) {
  return (
    <section className="bench" aria-label="The lawyer">
      <h1 className="bench__title">Love on Trial</h1>
      <div aria-live="polite">
        <Body
          view={view}
          mySeat={mySeat}
          thinking={thinking}
          inviteUrl={inviteUrl}
          onClaim={onClaim}
          onRetry={onRetry}
        />
      </div>
      {error && <p className="bench__error" role="alert">{error}</p>}
      {offline && <p className="bench__hint">Trying to reconnect…</p>}
      <footer className="bench__footer">
        <button className={view.decision ? "btn btn--light" : "linkish"} onClick={onStartOver}>
          Start a new case
        </button>
        <p className="disclaimer">Just for fun. Not legal advice or therapy.</p>
      </footer>
    </section>
  );
}
