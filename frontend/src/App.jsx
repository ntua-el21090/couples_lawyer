import { useEffect, useState } from "react";
import { api } from "./api.js";
import CasePage from "./CasePage.jsx";
import Gate from "./Gate.jsx";
import { ClipDefs, Heart } from "./Heart.jsx";
import Home from "./Home.jsx";
import { useCaseId } from "./routes.js";
import Splash from "./Splash.jsx";

export default function App() {
  const caseId = useCaseId();
  // Asked once: does this server want a passcode, and has this device entered it?
  const [session, setSession] = useState({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    setSession({ state: "loading" });
    api
      .session()
      .then((result) => current && setSession({ state: "ready", ...result }))
      .catch((error) => current && setSession({ state: "error", message: error.message }));
    return () => {
      current = false;
    };
  }, [attempt]);

  // The cookie ran out, or the server restarted and no longer knows it.
  const needLogin = () => setSession((s) => ({ ...s, authenticated: false }));

  let page;
  if (session.state === "loading") {
    page = (
      <Splash>
        <Heart className="beat splash__beat" />
        <p className="splash__text">Opening the court…</p>
      </Splash>
    );
  } else if (session.state === "error") {
    page = (
      <Splash>
        <p className="splash__text">{session.message}</p>
        <p className="splash__text">If the server was asleep, give it a minute.</p>
        <button className="btn btn--light" onClick={() => setAttempt((n) => n + 1)}>
          Try again
        </button>
      </Splash>
    );
  } else if (session.required && !session.authenticated) {
    page = <Gate onLogin={() => setSession((s) => ({ ...s, authenticated: true }))} />;
  } else if (caseId) {
    page = <CasePage key={caseId} id={caseId} onUnauthorized={needLogin} />;
  } else {
    page = <Home onUnauthorized={needLogin} />;
  }

  return (
    <>
      <ClipDefs />
      {page}
    </>
  );
}
