# AestheticLens API

阶段 1A 使用内存仓储和明确标识的 Mock 分析器验证 API 契约。`Repository` 与分析服务分离，后续可以替换为 PostgreSQL、对象存储和真实模型 Adapter。

启动：

```powershell
python -m uvicorn app.main:app --reload --app-dir backend
```

测试：

```powershell
python -m pytest backend/tests
```
