# AestheticLens API

阶段 1B-01 在内存仓储和 Mock 语义分析器之上增加真实、确定性的 SDR 影调与对比度提取。`Repository`、标准化适配器与提取器注册表彼此分离，后续可以替换存储或增加独立提取器。

方法、限制和引用见 `../docs/tone-contrast-methods.md` 和 `../docs/spatial-composition-methods.md`。

启动：

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

测试：

```powershell
python -m pytest
```
