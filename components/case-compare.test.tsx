import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { CompareButton, CompareProvider } from './case-compare';
import { ApiAnalysisProvider } from '@/lib/api-analysis-provider';
import type { AnalysisResult } from '@/lib/aesthetic-domain';

const cases = Array.from({ length: 4 }, (_, i) => ({
  asset_id: `a${i}`,
  result_id: `r${i}`,
  original_filename: `case${i}.png`,
  preview_url: `/image${i}`,
  tags: ['old-tag'],
  revision: 5,
  preview_text: 'old text',
}));
function Fixture() {
  return (
    <CompareProvider>
      {cases.map((item) => (
        <div key={item.result_id} data-testid={item.result_id}>
          <CompareButton item={item} />
        </div>
      ))}
    </CompareProvider>
  );
}
beforeEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

it('limits selection to three, removes and clears, and restores between pages', () => {
  const view = render(<Fixture />);
  for (let i = 0; i < 3; i++)
    fireEvent.click(within(screen.getByTestId(`r${i}`)).getByRole('button'));
  expect(within(screen.getByTestId('r3')).getByRole('button')).toBeDisabled();
  expect(
    within(screen.getByLabelText('对比托盘')).getAllByRole('img'),
  ).toHaveLength(3);
  view.unmount();
  render(<Fixture />);
  expect(
    within(screen.getByLabelText('对比托盘')).getAllByRole('img'),
  ).toHaveLength(3);
  fireEvent.click(screen.getByRole('button', { name: '移除 case0.png' }));
  expect(within(screen.getByTestId('r3')).getByRole('button')).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: '清空' }));
  expect(screen.queryByLabelText('对比托盘')).not.toBeInTheDocument();
  expect(
    JSON.parse(sessionStorage.getItem('aestheticlens-compare-v1')!),
  ).toEqual([]);
});

it('loads only selected details on start and compares final text/tags and existing metrics', async () => {
  const get = vi
    .spyOn(ApiAnalysisProvider.prototype, 'getResult')
    .mockImplementation(
      async (id) =>
        ({
          id,
          summary: 'Raw summary',
          intent: '',
          dimensions: [],
          tags: ['raw-tag'],
          warnings: [],
          completionStatus: 'complete',
          provenance: {
            mode: 'real',
            profileVersion: '1',
            pipelineVersion: '1',
          },
          humanRevision: {
            revision: 5,
            tags: [id === 'r0' ? 'human-cinematic' : 'human-minimalist'],
            dimensions: [
              'composition',
              'color',
              'lighting',
              'space',
              'style',
            ].map((code) => ({
              code,
              label: code,
              observation: 'human',
              interpretation: `reviewed ${code}`,
              review_status: 'accept',
              feedback_id: code,
            })),
          },
          features: [
            {
              extractor_code: 'tonal_occupancy',
              extractor_version: '1', feature_schema_version: '1', method: 'Metric', standard: null,
              parameters: {}, artifacts: [], provenance: {}, warnings: [], error_detail: null,
              status: 'succeeded',
              values: { shadow_share: id === 'r0' ? 0.4 : 0.2 },
            },
          ],
        }) as AnalysisResult,
    );
  render(<Fixture />);
  fireEvent.click(within(screen.getByTestId('r0')).getByRole('button'));
  fireEvent.click(within(screen.getByTestId('r1')).getByRole('button'));
  expect(get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '开始对比' }));
  await screen.findByText('human-cinematic');
  expect(get).toHaveBeenCalledTimes(2);
  expect(screen.getByText('human-cinematic').closest('td')).toHaveClass(
    'bg-amber-300/10',
  );
  expect(
    screen.getAllByText('reviewed composition')[0].closest('td'),
  ).not.toHaveClass('bg-amber-300/10');
  expect(screen.getByText('40.0%')).toBeInTheDocument();
  expect(screen.queryByText('raw-tag')).not.toBeInTheDocument();
  expect(screen.getAllByText(/^reviewed /)).toHaveLength(10);
});

it('keeps failed details explicit without replacing them with raw text', async () => {
  vi.spyOn(ApiAnalysisProvider.prototype, 'getResult').mockRejectedValue(
    new Error('offline'),
  );
  render(<Fixture />);
  fireEvent.click(within(screen.getByTestId('r0')).getByRole('button'));
  fireEvent.click(within(screen.getByTestId('r1')).getByRole('button'));
  fireEvent.click(screen.getByRole('button', { name: '开始对比' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('详情读取失败');
  expect(screen.queryByText('old text')).not.toBeInTheDocument();
});
