"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getAdvisorStatus,
  getLeagueRankings,
  streamAdvisorChat,
  type AdvisorMessage,
  type AdvisorPrompt,
  type AdvisorStatus,
  type RankingRow,
} from "@/lib/api";
import { AdvisorMarkdown } from "./AdvisorMarkdown";
import { useAdvisorContext } from "./AdvisorContext";

function MessageBubble({ role, content }: AdvisorMessage) {
  const isUser = role === "user";
  const display =
    isUser &&
    (content.startsWith("Base context (JSON):") ||
      content.startsWith("League context (JSON):"))
      ? content.split("\n\nQuestion:\n").pop() ?? content
      : content;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[92%] rounded-xl px-3 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "bg-bb-gold/15 text-white ring-1 ring-bb-gold/25 whitespace-pre-wrap"
            : "bg-white/5 text-bb-text ring-1 ring-white/10"
        }`}
      >
        {isUser ? display : <AdvisorMarkdown content={display} />}
      </div>
    </div>
  );
}

const MODEL_STORAGE_KEY = "bb-advisor-model-id";
const SIZE_STORAGE_KEY = "bb-advisor-panel-size";
const DEFAULT_PANEL_WIDTH = 420;
const DEFAULT_PANEL_HEIGHT = 640;
const MIN_PANEL_WIDTH = 300;
const MIN_PANEL_HEIGHT = 360;

type PanelSize = { width: number; height: number };

function readStoredPanelSize(): PanelSize {
  if (typeof window === "undefined") {
    return { width: DEFAULT_PANEL_WIDTH, height: DEFAULT_PANEL_HEIGHT };
  }
  try {
    const raw = window.localStorage.getItem(SIZE_STORAGE_KEY);
    if (!raw) {
      return { width: DEFAULT_PANEL_WIDTH, height: DEFAULT_PANEL_HEIGHT };
    }
    const parsed = JSON.parse(raw) as Partial<PanelSize>;
    const width =
      typeof parsed.width === "number" && parsed.width >= MIN_PANEL_WIDTH
        ? parsed.width
        : DEFAULT_PANEL_WIDTH;
    const height =
      typeof parsed.height === "number" && parsed.height >= MIN_PANEL_HEIGHT
        ? parsed.height
        : DEFAULT_PANEL_HEIGHT;
    return { width, height };
  } catch {
    return { width: DEFAULT_PANEL_WIDTH, height: DEFAULT_PANEL_HEIGHT };
  }
}

function clampPanelSize(size: PanelSize): PanelSize {
  if (typeof window === "undefined") return size;
  const margin = 40;
  return {
    width: Math.min(
      Math.max(size.width, MIN_PANEL_WIDTH),
      window.innerWidth - margin,
    ),
    height: Math.min(
      Math.max(size.height, MIN_PANEL_HEIGHT),
      window.innerHeight - margin,
    ),
  };
}

type AdvisorWidgetProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function AdvisorWidget({ open, onOpenChange }: AdvisorWidgetProps) {
  const {
    leagueId,
    myRosterId,
    focusedRosterId,
    setTradePerspectiveRosterId,
    pageContext,
  } = useAdvisorContext();
  const [status, setStatus] = useState<AdvisorStatus | null>(null);
  const [modelId, setModelId] = useState<string>("claude-sonnet-4-6");
  const [leagueTeams, setLeagueTeams] = useState<RankingRow[]>([]);
  const [messages, setMessages] = useState<AdvisorMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelSize, setPanelSize] = useState<PanelSize>(() =>
    clampPanelSize(readStoredPanelSize()),
  );
  const [isDesktop, setIsDesktop] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const threadKeyRef = useRef<string>("");

  const threadKey = `${leagueId ?? ""}:${focusedRosterId ?? ""}:${pageContext.pageType}`;

  useEffect(() => {
    if (threadKey !== threadKeyRef.current) {
      setMessages([]);
      threadKeyRef.current = threadKey;
    }
  }, [threadKey]);

  useEffect(() => {
    if (!leagueId) return;
    let cancelled = false;
    getLeagueRankings(leagueId)
      .then((rankings) => {
        if (cancelled) return;
        const teams = rankings.by_dynasty ?? [];
        setLeagueTeams(teams);
        if (
          focusedRosterId &&
          !teams.some((t) => t.roster_id === focusedRosterId) &&
          myRosterId
        ) {
          setTradePerspectiveRosterId(myRosterId);
        }
      })
      .catch(() => {
        if (!cancelled) setLeagueTeams([]);
      });
    return () => {
      cancelled = true;
    };
  }, [leagueId, focusedRosterId, myRosterId, setTradePerspectiveRosterId]);

  const perspectiveTeam = leagueTeams.find((t) => t.roster_id === focusedRosterId);
  const perspectiveLabel =
    focusedRosterId && focusedRosterId === myRosterId
      ? "My team"
      : perspectiveTeam?.team_name ??
        (focusedRosterId ? `Roster ${focusedRosterId}` : "My team");

  useEffect(() => {
    getAdvisorStatus()
      .then((next) => {
        setStatus(next);
        const stored =
          typeof window !== "undefined"
            ? window.localStorage.getItem(MODEL_STORAGE_KEY)
            : null;
        const storedModel = next.models.find((m) => m.id === stored && m.available);
        const fallback = next.models.find((m) => m.available);
        setModelId(storedModel?.id ?? fallback?.id ?? next.default_model);
      })
      .catch(() =>
        setStatus({
          configured: false,
          default_model: "claude-sonnet-4-6",
          models: [],
          prompts: [],
        }),
      );
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && modelId) {
      window.localStorage.setItem(MODEL_STORAGE_KEY, modelId);
    }
  }, [modelId]);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 640px)");
    const sync = () => setIsDesktop(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    const onResize = () => {
      setPanelSize((current) => clampPanelSize(current));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SIZE_STORAGE_KEY, JSON.stringify(panelSize));
    }
  }, [panelSize]);

  const startPanelResize = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const startSize = panelSize;

    const onMove = (moveEvent: PointerEvent) => {
      setPanelSize(
        clampPanelSize({
          width: startSize.width + (startX - moveEvent.clientX),
          height: startSize.height + (startY - moveEvent.clientY),
        }),
      );
    };

    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, [panelSize]);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming, open]);

  const send = useCallback(
    async (opts: { question?: string; promptId?: string; reset?: boolean }) => {
      const question = (opts.question ?? input).trim();
      if (!question || streaming || !leagueId) return;

      setError(null);
      setStreaming(true);

      const prior = opts.reset ? [] : messages;
      const isFirstTurn = prior.length === 0;
      const outbound: AdvisorMessage[] = [
        ...prior,
        { role: "user", content: question },
      ];
      setMessages(outbound);
      setInput("");

      let assistantText = "";
      setMessages([...outbound, { role: "assistant", content: "" }]);

      try {
        await streamAdvisorChat(
          {
            league_id: leagueId,
            question: isFirstTurn ? question : "",
            prompt_id: isFirstTurn ? (opts.promptId ?? null) : null,
            model_id: modelId,
            messages: isFirstTurn ? [] : outbound,
            focused_roster_id: focusedRosterId ?? null,
            page_context: {
              page_type: pageContext.pageType,
              path: pageContext.path ?? null,
              roster_id: pageContext.rosterId ?? null,
              player_id: pageContext.playerId ?? null,
              player_name: pageContext.playerName ?? null,
              summary: pageContext.summary ?? null,
            },
          },
          (chunk) => {
            assistantText += chunk;
            setMessages([
              ...outbound,
              { role: "assistant", content: assistantText },
            ]);
          },
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Advisor request failed";
        setError(msg);
        setMessages(prior);
      } finally {
        setStreaming(false);
      }
    },
    [input, leagueId, messages, modelId, streaming, focusedRosterId, pageContext],
  );

  const onPrompt = (prompt: AdvisorPrompt) => {
    setMessages([]);
    onOpenChange(true);
    void send({ question: prompt.question, promptId: prompt.id, reset: true });
  };

  if (!leagueId) return null;

  const configured = status?.configured ?? false;
  const prompts = status?.prompts ?? [];
  const models = status?.models ?? [];
  const selectedModel = models.find((m) => m.id === modelId);

  const contextLabel =
    pageContext.pageType === "team"
      ? pageContext.summary ?? "Team view"
      : pageContext.pageType === "player"
        ? pageContext.playerName ?? "Player view"
        : pageContext.pageType === "league"
          ? "League hub"
          : pageContext.pageType === "portfolio"
            ? "Portfolio"
            : pageContext.pageType === "rookie-draft"
              ? "Rookie draft"
              : "Dynasty advisor";

  return (
    <>
      {!open ? (
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] right-[max(1rem,env(safe-area-inset-right))] z-40 flex items-center gap-2 rounded-full border border-bb-gold/40 bg-[#0a0e14]/95 px-3 py-2 text-xs font-medium text-bb-gold shadow-lg shadow-black/40 backdrop-blur transition hover:border-bb-gold/60 hover:bg-bb-gold/10 sm:bottom-5 sm:right-5 sm:px-4 sm:py-2.5 sm:text-sm"
          title="Open dynasty advisor"
        >
          <span className="text-base">✦</span>
          Advisor
        </button>
      ) : null}

      {open ? (
        <aside
          className="fixed inset-0 z-50 flex flex-col overflow-hidden border-bb-border/60 bg-[#0a0e14]/98 pt-[env(safe-area-inset-top)] shadow-2xl shadow-black/50 backdrop-blur sm:inset-x-auto sm:inset-y-auto sm:bottom-5 sm:right-5 sm:left-auto sm:top-auto sm:rounded-2xl sm:border sm:pt-0"
          style={
            isDesktop
              ? { width: panelSize.width, height: panelSize.height }
              : undefined
          }
          role="dialog"
          aria-label="Dynasty advisor"
        >
          <header className="flex items-start justify-between border-b border-bb-border/50 px-4 py-3">
            <div className="min-w-0 pr-2">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-bb-gold">
                Advisor
              </p>
              <p className="truncate text-sm text-white">{contextLabel}</p>
              <p className="truncate text-xs text-bb-muted">
                Trades from: {perspectiveLabel}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="shrink-0 rounded-lg px-2 py-1 text-bb-muted transition hover:bg-white/5 hover:text-white"
              aria-label="Minimize advisor"
            >
              —
            </button>
          </header>

          {!configured ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
              <p className="text-sm text-bb-muted">
                Add <code className="text-bb-gold">ANTHROPIC_API_KEY</code> and/or{" "}
                <code className="text-bb-gold">MOONSHOT_API_KEY</code> to{" "}
                <code className="text-white">.env</code> and restart the API.
              </p>
            </div>
          ) : (
            <>
              <div className="border-b border-bb-border/40 px-3 py-2 space-y-2">
                {leagueTeams.length > 0 ? (
                  <label className="flex items-center gap-2 text-[11px] text-bb-muted">
                    <span className="shrink-0 uppercase tracking-wide">From</span>
                    <select
                      value={focusedRosterId ?? ""}
                      disabled={streaming}
                      onChange={(e) =>
                        setTradePerspectiveRosterId(e.target.value || undefined)
                      }
                      className="min-w-0 flex-1 rounded-md border border-bb-border/60 bg-black/30 px-2 py-1 text-xs text-white focus:border-bb-gold/50 focus:outline-none disabled:opacity-50"
                      title="Trade suggestions use this team's surplus and assets"
                    >
                      {leagueTeams.map((team) => (
                        <option key={team.roster_id} value={team.roster_id}>
                          {team.team_name ?? `Roster ${team.roster_id}`}
                          {team.roster_id === myRosterId ? " (me)" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                <label className="flex items-center gap-2 text-[11px] text-bb-muted">
                  <span className="shrink-0 uppercase tracking-wide">Model</span>
                  <select
                    value={modelId}
                    disabled={streaming}
                    onChange={(e) => setModelId(e.target.value)}
                    className="min-w-0 flex-1 rounded-md border border-bb-border/60 bg-black/30 px-2 py-1 text-xs text-white focus:border-bb-gold/50 focus:outline-none disabled:opacity-50"
                  >
                    {models.map((model) => (
                      <option
                        key={model.id}
                        value={model.id}
                        disabled={!model.available}
                      >
                        {model.label}
                        {!model.available ? " (no API key)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedModel && !selectedModel.supports_tools ? (
                  <p className="text-[10px] leading-snug text-amber-200/80">
                    Kimi uses base page context only — no live league tool calls. Use
                    Claude for trades, rosters, and suggest_trades.
                  </p>
                ) : null}
                <div className="flex flex-wrap gap-1.5">
                  {prompts.map((prompt) => (
                    <button
                      key={prompt.id}
                      type="button"
                      disabled={streaming}
                      onClick={() => onPrompt(prompt)}
                      className="rounded-full border border-bb-border/60 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-white transition hover:border-bb-gold/40 hover:bg-bb-gold/10 disabled:opacity-50"
                    >
                      {prompt.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-3 py-3">
                {messages.length === 0 ? (
                  <p className="text-center text-sm text-bb-muted">
                    Ask about trades, drops, or draft picks. Use{" "}
                    <span className="text-bb-gold">From</span> to explore what another
                    team in this league might trade.
                  </p>
                ) : null}
                {messages.map((msg, idx) => (
                  <MessageBubble key={`${idx}-${msg.role}`} {...msg} />
                ))}
                {streaming ? (
                  <p className="text-xs text-bb-muted animate-pulse">Thinking…</p>
                ) : null}
                {error ? (
                  <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">
                    {error}
                  </p>
                ) : null}
                <div ref={bottomRef} />
              </div>

              <form
                className="border-t border-bb-border/50 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:pb-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send({});
                }}
              >
                <div className="flex gap-2">
                  <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    disabled={streaming}
                    placeholder="Ask a follow-up…"
                    className="min-w-0 flex-1 rounded-lg border border-bb-border/60 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-bb-muted focus:border-bb-gold/50 focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={streaming || !input.trim()}
                    className="rounded-lg bg-bb-gold/20 px-3 py-2 text-sm font-medium text-bb-gold transition hover:bg-bb-gold/30 disabled:opacity-40"
                  >
                    Send
                  </button>
                </div>
              </form>
            </>
          )}

          {isDesktop ? (
            <button
              type="button"
              onPointerDown={startPanelResize}
              className="absolute bottom-0 left-0 z-10 hidden h-5 w-5 cursor-nwse-resize touch-none items-end justify-start rounded-bl-2xl p-1 text-bb-muted transition hover:text-bb-gold sm:flex"
              aria-label="Resize advisor panel"
              title="Drag to resize"
            >
              <svg
                viewBox="0 0 12 12"
                className="h-3 w-3"
                fill="currentColor"
                aria-hidden
              >
                <path d="M12 8v4H8l4-4zm-4 0v4H4l4-4zM8 0v4H4L8 0z" />
              </svg>
            </button>
          ) : null}
        </aside>
      ) : null}
    </>
  );
}
