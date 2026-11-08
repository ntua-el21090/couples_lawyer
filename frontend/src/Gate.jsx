import { useState } from "react";
import { api } from "./api.js";
import Splash from "./Splash.jsx";

export default function Gate({ onLogin }) {
  const [passcode, setPasscode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(passcode);
      onLogin();
    } catch (failure) {
      setError(failure.message);
      setBusy(false);
    }
  }

  return (
    <Splash>
      <p className="splash__text">This court is private. Enter the passcode you were given.</p>
      <form onSubmit={handleSubmit}>
        <input
          className="field"
          type="password"
          name="passcode"
          aria-label="Passcode"
          autoComplete="current-password"
          autoFocus
          maxLength={200}
          value={passcode}
          onChange={(event) => setPasscode(event.target.value)}
        />
        {error && <p className="bench__error" role="alert">{error}</p>}
        <button className="btn btn--light" type="submit" disabled={busy || !passcode}>
          {busy ? "Checking…" : "Enter the court"}
        </button>
      </form>
    </Splash>
  );
}
