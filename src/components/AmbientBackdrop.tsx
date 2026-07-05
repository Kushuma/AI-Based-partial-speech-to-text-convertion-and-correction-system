export function AmbientBackdrop() {
  return (
    <div className="ambient-backdrop" aria-hidden="true">
      <div className="ambient-backdrop__orb ambient-backdrop__orb--primary" />
      <div className="ambient-backdrop__orb ambient-backdrop__orb--secondary" />
      <div className="ambient-backdrop__grid" />
    </div>
  );
}

