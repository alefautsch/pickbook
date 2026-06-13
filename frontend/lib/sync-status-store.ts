import { getSyncStatus, invalidateSyncStatusCache, type SyncStatusResponse } from "./api";
import { SYNC_FINISHED_EVENT, SYNC_STARTED_EVENT } from "./sync-events";

const ACTIVE_POLL_MS = 5_000;
const MIN_FETCH_GAP_MS = 5_000;
const GLOBAL_KEY = "__bbSyncStatusStore";

type StoreState = {
  cache: SyncStatusResponse | null;
  lastFetchedAt: number;
  inflight: Promise<SyncStatusResponse | null> | null;
  activePollTimer: number | null;
  listeners: Set<() => void>;
  eventsBound: boolean;
  started: boolean;
};

function createState(): StoreState {
  return {
    cache: null,
    lastFetchedAt: 0,
    inflight: null,
    activePollTimer: null,
    listeners: new Set(),
    eventsBound: false,
    started: false,
  };
}

function getState(): StoreState {
  if (typeof window === "undefined") {
    return createState();
  }
  const w = window as Window & { [GLOBAL_KEY]?: StoreState };
  if (!w[GLOBAL_KEY]) {
    w[GLOBAL_KEY] = createState();
  }
  return w[GLOBAL_KEY];
}

function notify(state: StoreState) {
  for (const listener of state.listeners) {
    listener();
  }
}

async function fetchStatus(force = false): Promise<SyncStatusResponse | null> {
  const state = getState();
  const now = Date.now();

  if (!force && state.inflight) {
    return state.inflight;
  }
  if (!force && state.cache && now - state.lastFetchedAt < MIN_FETCH_GAP_MS) {
    return state.cache;
  }

  state.inflight = getSyncStatus()
    .then((data) => {
      state.cache = data;
      state.lastFetchedAt = Date.now();
      notify(state);
      return data;
    })
    .catch(() => {
      state.cache = null;
      notify(state);
      return null;
    })
    .finally(() => {
      state.inflight = null;
    });

  return state.inflight;
}

function stopActivePolling() {
  const state = getState();
  if (state.activePollTimer) {
    window.clearInterval(state.activePollTimer);
    state.activePollTimer = null;
  }
}

function startActivePolling() {
  const state = getState();
  stopActivePolling();
  state.activePollTimer = window.setInterval(() => void fetchStatus(), ACTIVE_POLL_MS);
}

function onSyncStart() {
  startActivePolling();
}

function onSyncEnd() {
  stopActivePolling();
  invalidateSyncStatusCache();
  void fetchStatus(true);
}

function bindEvents(state: StoreState) {
  if (state.eventsBound || typeof window === "undefined") return;
  window.addEventListener(SYNC_STARTED_EVENT, onSyncStart);
  window.addEventListener(SYNC_FINISHED_EVENT, onSyncEnd);
  state.eventsBound = true;
}

function ensureStarted() {
  const state = getState();
  if (state.started) return;
  state.started = true;
  bindEvents(state);
  void fetchStatus();
}

export function getSyncStatusCache(): SyncStatusResponse | null {
  return getState().cache;
}

export function subscribeSyncStatus(listener: () => void): () => void {
  const state = getState();
  state.listeners.add(listener);
  ensureStarted();
  if (state.cache) {
    listener();
  }

  return () => {
    state.listeners.delete(listener);
  };
}

export function forceRefreshSyncStatus(): Promise<SyncStatusResponse | null> {
  return fetchStatus(true);
}
