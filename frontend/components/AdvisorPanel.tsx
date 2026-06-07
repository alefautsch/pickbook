"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getAdvisorStatus,
  streamAdvisorChat,
  type AdvisorMessage,
  type AdvisorPrompt,
  type AdvisorStatus,
} from "@/lib/api";
import { AdvisorMarkdown } from "./AdvisorMarkdown";

type AdvisorPanelProps = {
  leagueId: string;
  open: boolean;
  onClose: () => void;
};

function MessageBubble({ role, content }: AdvisorMessage) {
  const isUser = role === "user";
  const display =
    isUser && content.startsWith("League context (JSON):")
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

export function AdvisorPanel({ leagueId, open, onClose }: AdvisorPanelProps) {
  const [status, setStatus] = useState<AdvisorStatus | null>(null);
  const [messages, setMessages] = useState<AdvisorMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const threadLeagueRef = useRef<string | null>(null);

  useEffect(() => {
    if (leagueId !== threadLeagueRef.current) {
      setMessages([]);
      threadLeagueRef.current = leagueId;
    }
  }, [leagueId]);

  useEffect(() => {
    if (!open) return;
    getAdvisorStatus()
      .then(setStatus)
      .catch(() =>
        setStatus({
          configured: false,
          default_model: "claude-sonnet-4-6",
          models: [],
          prompts: [],
        }),
      );
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const send = useCallback(
    async (opts: { question?: string; promptId?: string; reset?: boolean }) => {
      const question = (opts.question ?? input).trim();
      if (!question || streaming) return;

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
            model_id: status?.default_model ?? "claude-sonnet-4-6",
            messages: isFirstTurn ? [] : outbound,
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
    [input, leagueId, messages, status, streaming],
  );

  const onPrompt = (prompt: AdvisorPrompt) => {
    setMessages([]);
    void send({ question: prompt.question, promptId: prompt.id, reset: true });
  };

  if (!open) return null;

  const configured = status?.configured ?? false;
  const prompts = status?.prompts ?? [];

  return (
    <>
      <button
        type="button"
        aria-label="Close advisor"
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[1px]"
        onClick={onClose}
      />

      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-bb-border/60 bg-[#0a0e14] shadow-2xl"
        role="dialog"
        aria-label="Dynasty advisor"
      >
        <header className="flex items-center justify-between border-b border-bb-border/50 px-4 py-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.15em] text-bb-gold">
              Advisor
            </p>
            <p className="text-sm text-bb-muted">In-season dynasty analysis</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-bb-muted transition hover:bg-white/5 hover:text-white"
          >
            ✕
          </button>
        </header>

        {!configured ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <p className="text-sm text-bb-muted">
              Add <code className="text-bb-gold">ANTHROPIC_API_KEY</code> to your{" "}
              <code className="text-white">.env</code> and restart the API to enable
              the advisor.
            </p>
          </div>
        ) : (
          <>
            <div className="border-b border-bb-border/40 px-3 py-3">
              <div className="flex flex-wrap gap-2">
                {prompts.map((prompt) => (
                  <button
                    key={prompt.id}
                    type="button"
                    disabled={streaming}
                    onClick={() => onPrompt(prompt)}
                    className="rounded-full border border-bb-border/60 bg-white/5 px-3 py-1.5 text-xs font-medium text-white transition hover:border-bb-gold/40 hover:bg-bb-gold/10 disabled:opacity-50"
                  >
                    {prompt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
              {messages.length === 0 ? (
                <p className="text-center text-sm text-bb-muted">
                  Pick a prompt or ask about trades, drops, or rookie-draft prep.
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
              className="border-t border-bb-border/50 p-3"
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
      </aside>
    </>
  );
}
