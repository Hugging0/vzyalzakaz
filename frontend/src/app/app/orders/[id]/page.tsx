import { OrderDetailsPage } from "@/components/features/orders/OrderDetailsPage";

export default async function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <OrderDetailsPage id={Number(id)} />;
}
