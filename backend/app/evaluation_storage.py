"""Insert-only evaluation storage, independent of production feedback."""
from .evaluation import EvaluationCase, EvaluationRun, EvaluationFeedback


class EvaluationStorage:
    def save_evaluation_case(self, case):
        self._evaluation_insert("evaluation_cases", case)

    def get_evaluation_case(self, case_id):
        return self._evaluation_get("evaluation_cases", case_id, EvaluationCase)

    def list_evaluation_cases(self):
        return self._evaluation_list("evaluation_cases", EvaluationCase)

    def save_evaluation_run(self, run):
        self._evaluation_insert("evaluation_runs", run, "case_id")

    def get_evaluation_run(self, run_id):
        return self._evaluation_get("evaluation_runs", run_id, EvaluationRun)

    def save_evaluation_feedback(self, feedback):
        self._evaluation_insert("evaluation_feedback", feedback, "run_id")

    def list_evaluation_feedback(self, run_id):
        return self._evaluation_list("evaluation_feedback", EvaluationFeedback, run_id)


class MemoryEvaluationStorage(EvaluationStorage):
    def _evaluation_insert(self, table, value, parent=None):
        with self._review_lock:
            if value.id in self.evaluation_records[table]:
                raise ValueError("EVALUATION_RECORD_EXISTS")
            exists = (self.get_asset(value.asset_id) if table == "evaluation_cases" else
                      self.get_evaluation_case(value.case_id) if table == "evaluation_runs" else
                      self.get_evaluation_run(value.run_id))
            if exists is None:
                raise LookupError("EVALUATION_PARENT_NOT_FOUND")
            self.evaluation_records[table][value.id] = value.model_copy(deep=True)

    def _evaluation_get(self, table, record_id, model):
        value = self.evaluation_records[table].get(record_id)
        return value.model_copy(deep=True) if value else None

    def _evaluation_list(self, table, model, run_id=None):
        return [value.model_copy(deep=True) for value in
                sorted(self.evaluation_records[table].values(), key=lambda value: value.id)
                if run_id is None or value.run_id == run_id]


class PostgreSQLEvaluationStorage(EvaluationStorage):
    def _evaluation_insert(self, table, value, parent=None):
        from psycopg import sql
        from psycopg.types.json import Jsonb
        parent = parent or "asset_id"
        with self._connect() as connection:
            connection.execute(sql.SQL("INSERT INTO {} (id, {}, data) VALUES (%s, %s, %s)").format(
                sql.Identifier(table), sql.Identifier(parent)),
                (value.id, getattr(value, parent), Jsonb(value.model_dump(mode="json"))))

    def _evaluation_get(self, table, record_id, model):
        from psycopg import sql
        with self._connect() as connection:
            row = connection.execute(sql.SQL("SELECT data FROM {} WHERE id=%s").format(
                sql.Identifier(table)), (record_id,)).fetchone()
        return model.model_validate(row[0]) if row else None

    def _evaluation_list(self, table, model, run_id=None):
        from psycopg import sql
        query = sql.SQL("SELECT data FROM {}").format(sql.Identifier(table))
        if run_id is not None:
            query += sql.SQL(" WHERE run_id=%s")
        query += sql.SQL(" ORDER BY id")
        with self._connect() as connection:
            rows = connection.execute(query, (run_id,) if run_id is not None else ()).fetchall()
        return [model.model_validate(row[0]) for row in rows]
