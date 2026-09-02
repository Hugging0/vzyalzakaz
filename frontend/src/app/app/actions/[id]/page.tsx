import { ApplicationDetailsView } from "@/components/features/applications/ApplicationDetailsView";

export default async function ActionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ApplicationDetailsView id={Number(id)} />;
}
