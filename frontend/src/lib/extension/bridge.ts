type ExtensionMessage = { type: "LINK"; code: string } | { type: "CHECK_NOW" };

declare global {
  interface Window {
    chrome?: {
      runtime?: {
        sendMessage: (
          extensionId: string,
          message: ExtensionMessage,
          callback: (response: { ok?: boolean; error?: string } | undefined) => void,
        ) => void;
        lastError?: { message?: string };
      };
    };
  }
}

const extensionId = process.env.NEXT_PUBLIC_EXTENSION_ID;

export function canContactExtension(): boolean {
  return Boolean(extensionId && window.chrome?.runtime?.sendMessage);
}

export async function contactExtension(message: ExtensionMessage): Promise<boolean> {
  if (!extensionId || !window.chrome?.runtime?.sendMessage) return false;
  return new Promise((resolve) => {
    window.chrome!.runtime!.sendMessage(extensionId, message, (response) => {
      if (window.chrome?.runtime?.lastError || !response?.ok) resolve(false);
      else resolve(true);
    });
  });
}
