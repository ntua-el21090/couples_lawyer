import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import Bench from "./Bench.jsx";
import { Heart } from "./Heart.jsx";
import { caseUrl, createAndOpen } from "./routes.js";
import { forgetSeat, loadSeat, saveSeat } from "./seats.js";
import Side from "./Side.jsx";
import Splash from "./Splash.jsx";

const POLL_MS = 2000;
const PEOPLE = ["boy", "girl"];

function outcomeFor(person, verdict) {
  if (verdict === person) return "win";
  return verdict === "boy" || verdict === "girl" ? "lose" : null;
}

export default function CasePage({ id, onUnauthorized }) {
  const [view, setView] = useState(null);
  const [gone, setGone] = useState(false);
  const [offline, setOffline] = useState(null);
  const [seat, setSeat] = useState(() => loadSeat(id));
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [benchError, setBenchError] = useState(null);

  // Replies can arrive out of order, for example a poll started before a submit. Each
  // request takes a number when it starts, and a reply older than one already shown is
  // dropped. The next poll puts things right within a couple of seconds.
  const tickets = useRef({ issued: 0, applied: 0 });
  const begin = () => ++tickets.current.issued;
  const show = (ticket, next) => {
    if (ticket > tickets.current.applied) {
      tickets.current.applied = ticket;
      setView(next);
    }
  };
  const refresh = async () => {
    const ticket = begin();
    show(ticket, await api.getCase(id));
  };

  // Keep the page up to date with what the other person does, without a refresh.
  useEffect(() => {
    let stopped = false;
    let inFlight = false;
    let timer;

    async function poll() {
      if (stopped || inFlight) return;
      if (document.visibilityState === "visible") {
        inFlight = true;
        try {
          await refresh();
          if (!stopped) setOffline(null);
        } catch (error) {
          if (stopped) return;
          if (error.status === 404) return setGone(true); // stops polling
          if (error.status === 401) return onUnauthorized();
          setOffline(error.message);
        } finally {
          inFlight = false;
        }
      }
      if (!stopped) timer = setTimeout(poll, POLL_MS);
    }

    // A phone that was asleep catches up the moment it is looked at again.
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        clearTimeout(timer);
        poll();
      }
    };

    poll();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  function handleFailure(error) {
    if (error.status === 401) onUnauthorized();
    else if (error.status === 404) setGone(true);
  }

  async function claim(person) {
    try {
      const grant = await api.claimSeat(id, person);
      const claimed = { person: grant.person, token: grant.token };
      saveSeat(id, claimed);
      setSeat(claimed);
      refresh().catch(() => {});
    } catch (error) {
      handleFailure(error);
      refresh().catch(() => {}); // show who has the seats now
      throw error;
    }
  }

  async function submit(person, text) {
    const route = view.status === "awaiting_answers" ? "answers" : "statements";
    setSubmitting(true);
    try {
      const ticket = begin();
      show(ticket, await api.submit(id, route, person, text, seat.token));
    } catch (error) {
      handleFailure(error);
      throw error; // the column shows it, and keeps what was typed
    } finally {
      setSubmitting(false);
    }
  }

  async function retry() {
    setBenchError(null);
    setRetrying(true);
    try {
      const ticket = begin();
      show(ticket, await api.retry(id, seat.token));
    } catch (error) {
      setBenchError(error.message);
      handleFailure(error);
    } finally {
      setRetrying(false);
    }
  }

  async function startOver() {
    const inProgress = seat && view.status !== "decided";
    if (inProgress && !window.confirm("Start a new case? This one will end for both of you.")) return;
    setBenchError(null);
    try {
      const created = await api.createCase();
      if (seat) {
        await api.endCase(id, seat.token).catch(() => {});
        forgetSeat(id);
      }
      window.location.hash = `/c/${created.id}`;
    } catch (error) {
      setBenchError(error.message);
      handleFailure(error);
    }
  }

  if (gone) {
    return (
      <Splash title="This case is over">
        <p className="splash__text">
          It ended, or it timed out. Cases are cleared two hours after the last move, and whenever
          the server restarts.
        </p>
        <button className="btn btn--light" onClick={() => createAndOpen().catch((e) => setOffline(e.message))}>
          Start a new case
        </button>
        {offline && <p className="bench__error" role="alert">{offline}</p>}
      </Splash>
    );
  }

  if (!view) {
    return (
      <Splash>
        <Heart className="beat splash__beat" />
        <p className="splash__text">{offline ?? "Finding your case…"}</p>
      </Splash>
    );
  }

  const mySeat = seat?.person ?? null;
  // True for the person whose answer lets the lawyer start, from the moment they press send.
  const lastToSubmit = submitting && view.awaiting.length === 1 && view.awaiting[0] === mySeat;
  const thinking = view.status === "deliberating" || retrying || lastToSubmit;
  const verdict = view.decision?.verdict;

  return (
    <main className="court">
      {PEOPLE.map((person) => (
        <Side
          key={`${person}-${view.current_round}`}
          person={person}
          view={view}
          mine={person === mySeat}
          outcome={outcomeFor(person, verdict)}
          onSubmit={(text) => submit(person, text)}
        />
      ))}
      <Bench
        view={view}
        mySeat={mySeat}
        thinking={thinking}
        error={benchError}
        offline={offline}
        inviteUrl={caseUrl(id)}
        onClaim={claim}
        onRetry={retry}
        onStartOver={startOver}
      />
    </main>
  );
}
