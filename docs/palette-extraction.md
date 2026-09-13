# 主色板与强调色板

## 当前主色算法（保留）

入口：`backend/app/feature_pipeline.py::_dominant_palette`。

使用归一化、色彩管理后的分析图（最长边 2048），在 CIELAB D65 / 2° 空间
执行 SciPy `kmeans2`，初始化为 K-means++，随机种子 7，迭代 40 次。
按展平像素索引等距采样最多 20,000 点，最多聚成 5 类；实际类别数不超过
采样像素的不同颜色数。之后用 `vq` 将全图像素分配到中心，以像素数计算面积。
输出按面积递减，删除占比小于 2% 的类。聚类使用 Lab 欧氏距离；原有色差特征
`palette_color_contrast` 另用 CIEDE2000 计算主色之间的色差。

面积并不等于视觉重要性：小颜色可能未被采样，或因有限的五个聚类中心而并入
其他颜色；即使被独立聚出，占比低于 2% 仍会被过滤。4% 青蓝若成功形成独立类，
原算法本来就会保留；新功能解决的是额外的强调色识别与排序，不声称所有 4% 色块
都会被原算法遗漏。主色算法、原有 `colors/share/lab/lch/coverage` 字段及主色色差不变。

## 修改后的强调色算法原文说明

完整可执行源码：`backend/app/feature_pipeline.py::AccentPaletteExtractor`；
共享显著性源码：同文件 `_composition_saliency`。

1. 在同一分析图上计算 C*ab，筛选 C*ab ≥ 20 的像素。
2. 仅对这批有彩像素等距采样最多 20,000 点，复用同类 Lab K-means++ 方法，
   最多 8 类、种子 7、迭代 40 次。此分支补充候选，不修改原五类主色计算。
3. 将全部符合彩度门槛的像素分配到候选中心；各类计数除以全图总像素数得到
   `share`，`coverage_percentage = 100 * share`。不按有彩像素总数重新归一化。
4. 候选须占全图 0.1%–20%，中心 C*ab ≥ 20，且与大面积背景色的最小
   ΔE2000 ≥ 10。背景色取原主色板中面积 >20% 的项；若无此项，取面积第一项。
5. 复用构图模块的亮度梯度与局部纹理显著性：
   `S = GaussianSmooth(0.6 * gradient(Y) + 0.4 * local_std(Y))`。
   平滑尺度和可靠性门槛沿用构图配置；此函数提取保持旧构图计算公式完全相同。
   可靠时，`lift = mean(S in candidate) / mean(S globally)`；不可靠时不加分，
   `saliency_lift = null`。亮度显著性不是色彩或语义注意模型，不作为硬性筛除条件。
6. 按下式评分、递减排序；分数相同按面积、再按色值稳定排序：

   ```text
   support = sqrt(min(share / 0.04, 1))
   chroma_strength = C / (C + 20)
   contrast_strength = ΔE / (ΔE + 10)
   bonus = max(0, (lift - 1) / (lift + 1))  # 不可靠时为 0
   score = support * chroma_strength * contrast_strength * (1 + 0.5 * bonus)
   ```

7. 按排名依次保留颜色，若与已保留颜色 ΔE2000 < 8 则去重，最多保留 3 色。
   去重项的面积不合并；各项面积仍对应其原候选类。

上述门槛是可配置的工程启发式，不是通用感知阈值或正确概率。强调色仍需人工审核；
稀有颜色低于 0.1%、原图缩小后消失、近似颜色被合并，或复杂彩色图中候选聚类不足时
仍可能漏检。本版侧重有彩点缀；灰阶、低彩度或纯明暗强调不强行输出色彩强调。

## API 输出与兼容

沿用 `features` 数组，不改变顶层接口或数据库：

```json
{
  "features": [
    {"extractor_code": "dominant_palette", "values": {
      "colors": [
        {"rank": 1, "hex_srgb": "#000000", "share": 0.80},
        {"rank": 2, "hex_srgb": "#282828", "share": 0.16},
        {"rank": 3, "hex_srgb": "#00B4DC", "share": 0.04}
      ]
    }},
    {"extractor_code": "accent_palette", "values": {
      "defined": true,
      "colors": [{"rank": 1, "hex_srgb": "#00B4DC", "share": 0.04, "coverage_percentage": 4.0}]
    }}
  ]
}
```

示例省略原有 FeatureResult 元数据及 Lab/LCh、色差、彩度、显著性和排序分数。
同一颜色可以同时属于两个板，面积不可跨板累加。强调色配置及版本进入原有
`FeatureResult.parameters`，新 extractor/schema 版本为 1.0.0。
前端分别展示主色板和强调色板，并兼容缺少 `accent_palette` 的历史结果。
历史结果不会被自动重写；重新分析后才会得到强调色。

配置：`backend/config/analysis_profiles.json` → `feature_pipeline.color_analysis.accent_palette`。
