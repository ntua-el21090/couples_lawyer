// A small centred card, for the screens that come before or instead of the court.
export default function Splash({ title = "Love on Trial", children }) {
  return (
    <main className="splash">
      <div className="splash__card">
        <h1 className="splash__title">{title}</h1>
        {children}
      </div>
    </main>
  );
}
