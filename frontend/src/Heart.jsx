// A whole heart, used for the verdict and the loading beat.
export function Heart({ className }) {
  return (
    <svg className={className} viewBox="0 0 100 90" aria-hidden="true">
      <path d="M50 88 C20 64 2 46 2 26 C2 11 14 2 27 2 C37 2 45 7 50 16 C55 7 63 2 73 2 C86 2 98 11 98 26 C98 46 80 64 50 88 Z" />
    </svg>
  );
}

// Half-heart shapes the photos are cut to, in coordinates of 0 to 1 so they scale with the
// photo. Rendered once at the top of the page.
export function ClipDefs() {
  return (
    <svg width="0" height="0" aria-hidden="true" className="clip-defs">
      <defs>
        <clipPath id="heart-left" clipPathUnits="objectBoundingBox">
          <path d="M1 .18 C.88 .03 .62 0 .44 0 C.18 0 0 .18 0 .42 C0 .78 .68 .9 1 1 L.86 .82 L1 .66 L.82 .5 L.98 .35 Z" />
        </clipPath>
        <clipPath id="heart-right" clipPathUnits="objectBoundingBox">
          <path
            transform="matrix(-1 0 0 1 1 0)"
            d="M1 .18 C.88 .03 .62 0 .44 0 C.18 0 0 .18 0 .42 C0 .78 .68 .9 1 1 L.86 .82 L1 .66 L.82 .5 L.98 .35 Z"
          />
        </clipPath>
      </defs>
    </svg>
  );
}

const ALT = { boy: "The boy", girl: "The girl" };

// A person's photo as half a heart. The photos come from the backend, which only
// sends them to people who have entered the passcode.
export function HeartPhoto({ person, outcome }) {
  return (
    <div className={`heart heart--${person} ${outcome ? `heart--${outcome}` : ""}`}>
      <div className="heart__shape">
        <img src={`/api/photos/${person}.jpg`} alt={ALT[person]} />
      </div>
      {outcome && <span className="heart__stamp">{outcome === "win" ? "Right!" : "Oof"}</span>}
    </div>
  );
}
