"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { HuntApp } from "@/components/features/telegram-shell/HuntApp";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

export default function MiniAppPage() {
  const [client] = useState(() => queryClient);
  return (
    <QueryClientProvider client={client}>
      <HuntApp />
    </QueryClientProvider>
  );
}
