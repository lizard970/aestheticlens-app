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

持久化存储（未设置时仍使用内存仓储）：

```powershell
$env:AESTHETICLENS_DATABASE_URL='postgresql://USER:PASSWORD@localhost:5432/aestheticlens'
python -m app.migrate
python -m uvicorn app.main:app --reload --port 8000
```

如需运行 PostgreSQL 重启持久化集成测试，将同一测试数据库连接串设置为
`AESTHETICLENS_TEST_DATABASE_URL`。

语义检索需要 PostgreSQL 安装 pgvector 扩展，并配置 `.env.example` 中的
`AESTHETICLENS_EMBEDDING_*`。`python -m app.migrate` 会创建扩展、1536 维向量表和
cosine HNSW 索引。首次启用时运行 `python -m app.reindex_embeddings`，为已有合格案例
补建向量。当前只调用外部 OpenAI embeddings API，不下载或托管模型。
