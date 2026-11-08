// The case lives in the address after the #, like /#/c/<id>, so the server needs no
// special handling for it and the link can be sent to the other person.

import { useEffect, useState } from "react";
import { api } from "./api.js";

const CASE_HASH = /^#\/c\/([0-9a-f-]{36})$/i;

export function parseCaseId(hash) {
  return CASE_HASH.exec(hash)?.[1] ?? null;
}

export function caseUrl(id) {
  return `${window.location.origin}${window.location.pathname}#/c/${id}`;
}

export function openCase(id) {
  window.location.hash = `/c/${id}`;
}

export async function createAndOpen() {
  const created = await api.createCase();
  openCase(created.id);
  return created;
}

export function useCaseId() {
  const [id, setId] = useState(() => parseCaseId(window.location.hash));
  useEffect(() => {
    const onChange = () => setId(parseCaseId(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return id;
}
