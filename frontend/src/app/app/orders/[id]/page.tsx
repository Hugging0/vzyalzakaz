import { OrderDetailsPage } from "@/components/features/orders/OrderDetailsPage";

export default async function OrderPage({ params, searchParams }: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
}) {
  const { id } = await params;
  const { returnTo } = await searchParams;
  const safeReturnTo = typeof returnTo === "string" && (returnTo === "/app/orders" || returnTo.startsWith("/app/orders?")) ? returnTo : "/app/orders";
  return <OrderDetailsPage id={Number(id)} returnTo={safeReturnTo} />;
}
