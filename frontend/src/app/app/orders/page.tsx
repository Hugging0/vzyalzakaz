import { Suspense } from "react";
import { OrdersView } from "@/components/features/orders/OrdersView";
import { FeedSkeleton } from "@/components/ui/States";

export default function OrdersPage() {
  return <Suspense fallback={<FeedSkeleton />}><OrdersView /></Suspense>;
}
