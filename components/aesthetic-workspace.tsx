'use client';

import { ColorComputationalFeatures } from '@/components/color-computational-features';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, BookOpenText, ChevronRight, CircleAlert, FlaskConical, ImagePlus, Layers3, LoaderCircle, MessageSquareText, Search, SlidersHorizontal, Sparkles, Upload, Video } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress, ProgressLabel, ProgressValue } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { DEFAULT_ANALYSIS_PROFILE } from '@/lib/analysis-profile';
import type { AnalysisResult, AnalysisStage, UploadedAsset } from '@/lib/aesthetic-domain';
import { DimensionReview } from '@/components/dimension-review';
import { ResultHistory } from '@/components/result-history';
import { ApiAnalysisProvider } from '@/lib/api-analysis-provider';
import { ComputationalFeatures } from '@/components/computational-features';
import { analysisPresentation } from '@/lib/analysis-presentation';
import { SemanticStatus } from '@/components/semantic-status';
import { CompositionComputationalFeatures, SpaceComputationalFeatures } from '@/components/spatial-composition-features';


const stageMeta: Record<AnalysisStage, { label: string; progress: number }> = {
  idle: { label: '等待素材', progress: 0 }, ready: { label: '素材已就绪', progress: 8 },
  extracting: { label: '提取视觉特征', progress: 38 }, analyzing: { label: '生成维度分析', progress: 72 },
  building: { label: '构建证据引用', progress: 91 }, complete: { label: '分析完成', progress: 100 },
};

const navItems = [
  { label: '素材分析', icon: Aperture, active: true, available: true },
  { label: '视频镜头', icon: Video, active: false, available: false },
  { label: '视觉知识库', icon: BookOpenText, active: false, available: false },
  { label: '对比与检索', icon: Search, active: false, available: false },
  { label: '模型评测', icon: FlaskConical, active: false, available: false },
  { label: '审美档案', icon: Sparkles, active: false, available: false },
];

const provider = new ApiAnalysisProvider();
const wait = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function createAsset(file: File): Promise<UploadedAsset> {
  const previewUrl = URL.createObjectURL(file);
  const dimensions = await new Promise<{ width: number; height: number }>((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
    image.onerror = () => reject(new Error('invalid image'));
    image.src = previewUrl;
  });
  return { id: crypto.randomUUID(), file, previewUrl, ...dimensions };
}

export function AestheticWorkspace() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [asset, setAsset] = useState<UploadedAsset | null>(null);
  const [stage, setStage] = useState<AnalysisStage>('idle');
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selection = useRef(0);
  const status = stageMeta[stage];
  const presentation = analysisPresentation(result);
  const isRunning = ['extracting', 'analyzing', 'building'].includes(stage);
  const previewUrl = asset?.previewUrl ?? result?.previewUrl;

  useEffect(() => () => { if (asset) URL.revokeObjectURL(asset.previewUrl); }, [asset]);

  const fileMeta = useMemo(() => asset ? `${asset.width} × ${asset.height} · ${(asset.file.size / 1024 / 1024).toFixed(2)} MB` : null, [asset]);

  useEffect(() => {
    const id = new URL(window.location.href).searchParams.get('result_id');
    if (!id) return;
    let active = true;
    const version = selection.current;
    void provider.getResult(id).then(restored => {
      if (active && version === selection.current) { setResult(restored); setStage('complete'); }
    }).catch(() => { if (active && version === selection.current) setError('历史结果不可用；当前内存仓储在服务重启后会清空。'); });
    return () => { active = false; };
  }, []);

  function rememberResult(id?: string) {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set('result_id', id); else url.searchParams.delete('result_id');
    window.history.replaceState(null, '', url);
  }

  async function openHistory(id: string) {
    const version = ++selection.current;
    try {
      const restored = await provider.getResult(id);
      if (version !== selection.current) return;
      setAsset(null); setResult(restored); setStage('complete'); setError(null); rememberResult(id);
    } catch { if (version === selection.current) setError('历史结果读取失败，请重试。'); }
  }

  async function handleFile(file?: File) {
    if (!file) return;
    selection.current += 1;
    rememberResult(); setError(null); setResult(null);
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('当前支持 JPG、PNG 和 WebP 图片。'); return;
    }
    try {
      const nextAsset = await createAsset(file);
      setAsset((current) => { if (current) URL.revokeObjectURL(current.previewUrl); return nextAsset; });
      setStage('ready');
    } catch {
      setError('图片读取失败，请检查文件是否损坏。'); setStage('idle');
    }
  }

  async function runAnalysis() {
    if (!asset || isRunning) return;
    const version = ++selection.current;
    setError(null); setResult(null);
    try {
      setStage('extracting'); await wait(450);
      setStage('analyzing'); const nextResult = await provider.analyze(asset);
      if (version !== selection.current) return;
      setStage('building'); await wait(350);
      if (version !== selection.current) return;
      setResult(nextResult); setStage('complete'); rememberResult(nextResult.id);
    } catch {
      if (version !== selection.current) return;
      setError('分析任务未完成，请重新运行。'); setStage('ready');
    }
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-white/8 bg-background/88 px-4 backdrop-blur-xl lg:px-6">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-xl border border-amber-300/25 bg-amber-300/8 text-amber-300"><Aperture className="size-5" /></div>
          <div><p className="text-base font-semibold tracking-tight">AestheticLens</p><p className="text-xs text-muted-foreground">美学评测工作台</p></div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="border-cyan-300/25 text-cyan-200">{presentation.pipeline}</Badge>
          <Button variant="outline" size="sm" className="border-white/10 bg-white/3"><SlidersHorizontal data-icon="inline-start" />分析配置</Button>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1600px] lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden min-h-[calc(100vh-4rem)] border-r border-white/8 p-4 lg:block">
          <nav aria-label="主要功能" className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return <button key={item.label} type="button" disabled={!item.available} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${item.active ? 'bg-amber-300/10 text-amber-100' : 'text-muted-foreground hover:bg-white/4 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-45'}`}>
                <Icon className="size-4" /><span>{item.label}</span>{!item.available && <span className="ml-auto text-[11px]">后续</span>}
              </button>;
            })}
          </nav>
          <div className="mt-8 rounded-2xl border border-cyan-300/12 bg-cyan-300/5 p-4"><p className="text-xs font-medium text-cyan-200">当前里程碑</p><p className="mt-2 text-sm leading-6 text-muted-foreground">跑通单图上传、任务状态、结构化结果和反馈闭环。</p></div>
        </aside>

        <section className="min-w-0 p-4 lg:p-6">
          <ResultHistory load={() => provider.history()} onSelect={id => void openHistory(id)} disabled={isRunning} />
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div><p className="mb-1 text-xs font-medium uppercase tracking-[0.18em] text-amber-300/80">Frame review 001</p><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">素材分析</h1></div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground"><span>{DEFAULT_ANALYSIS_PROFILE.name}</span><ChevronRight className="size-4" /><span>v{DEFAULT_ANALYSIS_PROFILE.version}</span></div>
          </div>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.08fr)_minmax(420px,.92fr)]">
            <section className="overflow-hidden rounded-2xl border border-white/9 bg-card shadow-2xl shadow-black/15">
              <div className="flex items-center justify-between border-b border-white/8 px-4 py-3"><div className="flex items-center gap-2"><Layers3 className="size-4 text-amber-300" /><h2 className="text-sm font-medium">画面与证据层</h2></div>{asset && <span className="text-xs text-muted-foreground">{fileMeta}</span>}</div>
              <div className="relative flex aspect-[16/10] min-h-[360px] items-center justify-center bg-[#090b0d] p-5" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); void handleFile(event.dataTransfer.files[0]); }}>
                {previewUrl ? <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={previewUrl} alt="待分析素材" className="max-h-full max-w-full object-contain shadow-2xl" />
                </> : <button type="button" onClick={() => inputRef.current?.click()} className="group flex max-w-md flex-col items-center rounded-2xl border border-dashed border-white/15 px-8 py-12 text-center transition hover:border-amber-300/45 hover:bg-amber-300/4">
                  <span className="mb-4 flex size-12 items-center justify-center rounded-2xl bg-white/5 text-muted-foreground transition group-hover:text-amber-300"><ImagePlus className="size-6" /></span>
                  <span className="font-medium">拖入一张画面，或点击选择文件</span><span className="mt-2 text-sm text-muted-foreground">JPG、PNG、WebP · 本阶段只处理单张图片</span>
                </button>}
                <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(event) => void handleFile(event.target.files?.[0])} />
              </div>
              <div className="border-t border-white/8 p-4">
                {error && <div role="alert" className="mb-3 flex items-center gap-2 rounded-xl border border-red-400/20 bg-red-400/8 px-3 py-2 text-sm text-red-200"><CircleAlert className="size-4" />{error}</div>}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-[220px] flex-1"><Progress value={status.progress} className="[&_[data-slot=progress-indicator]]:bg-amber-300 [&_[data-slot=progress-track]]:bg-white/8"><ProgressLabel className="text-sm">{status.label}</ProgressLabel><ProgressValue /></Progress></div>
                  <div className="flex gap-2">{previewUrl && <Button variant="outline" onClick={() => inputRef.current?.click()} disabled={isRunning} className="border-white/10 bg-white/3"><Upload data-icon="inline-start" />更换图片</Button>}<Button onClick={() => void runAnalysis()} disabled={!asset || isRunning} className="bg-amber-300 text-black hover:bg-amber-200">{isRunning ? <LoaderCircle className="animate-spin" data-icon="inline-start" /> : <Sparkles data-icon="inline-start" />}{result ? '重新分析' : '开始分析'}</Button></div>
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-white/9 bg-card p-4 sm:p-5">
              {!result ? <div className="flex min-h-[520px] flex-col items-center justify-center text-center"><div className="mb-4 flex size-12 items-center justify-center rounded-2xl border border-cyan-300/15 bg-cyan-300/6 text-cyan-200"><MessageSquareText className="size-6" /></div><h2 className="text-lg font-medium">分析结果将在这里展开</h2><p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">上传图片后，系统会依次展示任务进度、五维判断、证据和反馈入口。</p></div> : <>
                <div className="mb-4"><div className="mb-2 flex items-center gap-2"><Badge className="bg-cyan-300 text-black">{presentation.pipeline}</Badge>{result.completionStatus === 'partial' && <Badge variant="destructive">部分完成</Badge>}<span className="font-mono text-xs text-muted-foreground">{result.id.slice(0, 8)}</span></div><h2 className="text-lg font-semibold">{result.summary}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{result.intent}</p></div>
                <SemanticStatus result={result} />
                <Tabs defaultValue={result.dimensions[0]?.code}>
                  <TabsList variant="line" className="w-full justify-start overflow-x-auto border-b border-white/8 pb-2">{result.dimensions.map((dimension) => <TabsTrigger key={dimension.code} value={dimension.code} className="px-3">{dimension.label}</TabsTrigger>)}</TabsList>
                  {result.dimensions.map((dimension) => (
  <TabsContent
    key={dimension.code}
    value={dimension.code}
    className="pt-4"
  >
    <div className="space-y-4">

      {dimension.code === 'lighting' && (
        <ComputationalFeatures
          features={result.features}
          completionStatus={result.completionStatus}
          resultWarnings={result.warnings}
        />
      )}

      {dimension.code === 'color' && (
        <ColorComputationalFeatures
          features={result.features}
        />
      )}

      {dimension.code === 'space' && (
        <SpaceComputationalFeatures
          features={result.features}
        />
      )}

      {dimension.code === 'composition' && (
        <CompositionComputationalFeatures
          features={result.features}
        />
      )}

      <div className="rounded-xl bg-white/3 p-4">
        <p className="text-xs font-medium text-cyan-200">
          原始观察
        </p>
        <p className="mt-2 leading-6">
          {dimension.observation}
        </p>
      </div>

      <div className="rounded-xl border border-amber-300/12 bg-amber-300/5 p-4">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium text-amber-200">
            原始解释
          </p>

          <span className="font-mono text-xs text-muted-foreground">
            {presentation.confidence}
          </span>
        </div>

        <p className="mt-2 leading-6">
          {dimension.interpretation}
        </p>
      </div>

      <div>
        {dimension.code === 'style' && <p className="mb-2 text-sm">风格标签：{result.tags.length ? result.tags.join(' · ') : '暂无可确认标签'}</p>}
        <DimensionReview key={`${result.id}:${dimension.code}`} result={result} dimension={dimension}
          save={(id, feedback) => provider.saveFeedback(id, feedback)}
          onSaved={updated => setResult(current => current?.id === updated.id && (updated.humanRevision?.revision ?? 0) >= (current.humanRevision?.revision ?? 0) ? updated : current)} />
      </div>

    </div>
  </TabsContent>
))}
                </Tabs>
              </>}
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}
