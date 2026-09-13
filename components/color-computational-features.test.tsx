import { render, screen, within } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ColorComputationalFeatures } from './color-computational-features';
import type { FeatureResult } from '@/lib/aesthetic-domain';

const dominant: FeatureResult = {
  extractor_code: 'dominant_palette', extractor_version: '1.0.0', feature_schema_version: '1.0.0', method: '', standard: null,
  status: 'succeeded', parameters: {}, values: { colors: [{ rank: 1, hex_srgb: '#000000', share: .8 }] }, artifacts: [], provenance: {}, warnings: [], error_detail: null,
};

it('separates area and accent palettes while keeping legacy results readable', () => {
  const { rerender } = render(<ColorComputationalFeatures features={[dominant]} />);
  expect(screen.getByText('此历史结果尚未提取强调色')).toBeInTheDocument();
  rerender(<ColorComputationalFeatures features={[dominant, { ...dominant, extractor_code: 'accent_palette', values: { colors: [{ rank: 1, hex_srgb: '#00B4DC', share: .04 }] } }]} />);
  expect(within(screen.getByRole('article', { name: '主色板 · 面积排序' })).getByText('80.0%')).toBeInTheDocument();
  const accents = within(screen.getByRole('article', { name: '强调色板 · 视觉强调排序' }));
  expect(accents.getByText('#00B4DC')).toBeInTheDocument();
  expect(accents.getByText('4.0%')).toBeInTheDocument();
  rerender(<ColorComputationalFeatures features={[dominant, { ...dominant, extractor_code: 'accent_palette', values: { colors: [] } }]} />);
  expect(screen.getByText('未检出符合条件的小面积强调色')).toBeInTheDocument();
});
