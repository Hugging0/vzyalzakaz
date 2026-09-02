import type { StoredState } from "./contracts";

const STATE_KEY = "vzyalzakazState";

const defaultState = (): StoredState => ({
  installationId: crypto.randomUUID().replaceAll("-", "_"),
  token: null,
  connection: "DISCONNECTED",
  lastHeartbeatAt: null,
  activeSourceId: null,
  marketplaceAuthState: "UNKNOWN",
  activeCommand: null,
  lastError: null,
});

export async function getState(): Promise<StoredState> {
  const stored = await chrome.storage.local.get(STATE_KEY);
  const value = stored[STATE_KEY] as StoredState | undefined;
  if (value) return value;
  const initial = defaultState();
  await chrome.storage.local.set({ [STATE_KEY]: initial });
  return initial;
}

export async function updateState(patch: Partial<StoredState>): Promise<StoredState> {
  const next = { ...(await getState()), ...patch };
  await chrome.storage.local.set({ [STATE_KEY]: next });
  return next;
}

export async function clearSession(): Promise<StoredState> {
  const current = await getState();
  const next: StoredState = {
    ...defaultState(),
    installationId: current.installationId,
  };
  await chrome.storage.local.set({ [STATE_KEY]: next });
  return next;
}
