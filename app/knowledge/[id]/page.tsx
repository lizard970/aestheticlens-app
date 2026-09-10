import { KnowledgeDetail } from '@/components/knowledge-detail';
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <KnowledgeDetail key={id} id={id} />;
}
