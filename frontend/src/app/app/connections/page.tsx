import { Suspense } from "react";

import { ConnectionsView } from "@/components/features/connections/ConnectionsView";

export default function ConnectionsPage() {
  return <Suspense fallback={null}><ConnectionsView /></Suspense>;
}
