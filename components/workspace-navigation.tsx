'use client';
import Link from 'next/link';
import { Aperture, BookOpenText, Search } from 'lucide-react';
import { CompareProvider } from './case-compare';

export function WorkspaceNavigation({ active }: { active: string }) {
  const items = [
    { label: '素材分析', href: '/', icon: Aperture },
    { label: '视觉知识库', href: '/knowledge', icon: BookOpenText },
    { label: '对比与检索', href: '/search', icon: Search },
  ];
  return (
    <aside className="border-b border-white/10 p-3 lg:border-r">
      <nav
        aria-label="主要功能"
        className="flex gap-1 overflow-auto lg:flex-col"
      >
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active === item.href ? 'page' : undefined}
            className={`flex shrink-0 items-center gap-2 rounded-lg p-3 text-sm ${active === item.href ? 'bg-amber-300/10 text-amber-100' : 'text-muted-foreground hover:bg-white/5'}`}
          >
            <item.icon className="size-4" />
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}

export function WorkspacePage({
  active,
  children,
}: {
  active: string;
  children: React.ReactNode;
}) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="flex h-16 items-center gap-3 border-b border-white/10 px-5">
        <Aperture className="size-6 text-amber-300" />
        <div>
          <p className="font-semibold">AestheticLens</p>
          <p className="text-sm text-muted-foreground">
            人工审核闭环的视觉分析系统
          </p>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1800px] lg:grid-cols-[180px_minmax(0,1fr)]">
        <WorkspaceNavigation active={active} />
        <CompareProvider><section className="min-w-0 space-y-4 p-5 pb-28">{children}</section></CompareProvider>
      </div>
    </main>
  );
}
