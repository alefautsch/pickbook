const DYNASTY_DEALER_URL = "https://www.dynastydealer.com";

export function MarketAttribution({ className = "" }: { className?: string }) {
  return (
    <p className={`text-[10px] leading-relaxed text-bb-muted ${className}`}>
      Player and pick trade values blend Dynasty Daddy, KeepTradeCut, and trade-derived data from{" "}
      <a
        href={DYNASTY_DEALER_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="text-bb-muted underline decoration-white/20 underline-offset-2 hover:text-white"
      >
        Dynasty Dealer
      </a>
      . OVR includes blended TV (~45% of the dynasty composite).
    </p>
  );
}
