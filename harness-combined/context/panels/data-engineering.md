## Data Engineering, Analytics Engineering & ML Systems Panel

*Active when data-pipeline or ML systems code is in scope: Airflow (`dags/**/*.py`, `airflow.cfg`, `@dag`/`DAG(...)` constructions), Dagster (`@asset`, `@op`, `Definitions`, `dagster.yaml`), Prefect (`@flow`, `@task`); dbt projects (`dbt_project.yml`, `models/**/*.sql`, `**/schema.yml`, `seeds/`, `snapshots/`, `macros/`); Spark/PySpark (`SparkSession`, `pyspark.sql`, `org.apache.spark`); Apache Beam pipelines; data-warehouse SQL (BigQuery, Snowflake, Redshift, Databricks); training pipelines and ML serving code (`scikit-learn`, `xgboost`, `pytorch`, `tensorflow`, `mlflow`, `kubeflow`, feature stores like Feast/Tecton). Generic OLTP database concerns defer to the Database panel; this panel covers the analytical and ML-specific data layer where the cost profile, correctness model, and failure modes are different.*

- **Maxime Beauchemin** — creator of Apache Airflow and Apache Superset; founder of Preset; the "functional data engineering" framing — idempotent tasks, immutable inputs, deterministic outputs, backfill as a first-class operation
- **Tristan Handy** — founder of dbt Labs; the "analytics engineering" movement — analytics-as-software-engineering, model layering (staging → intermediate → marts), tests as first-class, the semantic layer as contract
- **D. Sculley** — lead author of *Hidden Technical Debt in Machine Learning Systems* (2015); the canonical reference on ML-specific failure modes — training/serving skew, feedback loops, glue code, undeclared consumers, the CACE (Changing Anything Changes Everything) property

**Beauchemin's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Functional data engineering: tasks must be idempotent** | Running a task twice with the same inputs must produce the same outputs and the same side effects. Idempotency is what makes backfill, retry, and replay safe operations rather than incident-producing ones. The canonical violation: a task that `INSERT`s rows without a deduplication key, or sends notifications, or increments a counter — each execution diverges from the prior. |
| **Backfill is a first-class operation** | Data engineering's equivalent of "rebuild the world." If you cannot rerun yesterday's pipeline today and produce the same result, you have a different kind of system — one whose history depends on when the code was run, not on the code itself. Tasks parameterized by `execution_date` (Airflow) / `logical_date` (Airflow 2+), reading partitioned inputs and writing partitioned outputs, support this. Tasks reading "the current state of X" do not. |
| **Tasks read partitions, write partitions** | The unit of input and output is a partition — a date, a window, a partition key. Writing into a mutable destination ("the customers table") instead of a partitioned location ("the customers table partitioned by load_date") makes the result depend on order of execution; sequential retries produce different state than parallel ones. |
| **The DAG is the API; logic lives in tasks** | The orchestration graph (which tasks run when, depending on what) is a contract: schedules, dependencies, retry policy, SLAs. Business logic belongs in the tasks the graph invokes. DAGs containing inline computation, large XCom passes, or branching that depends on data the orchestrator shouldn't know about are conflating the two. |
| **Late-arriving data is a design problem, not a runtime exception** | Some events arrive hours, days, or weeks after the timestamp they belong to. A pipeline that processes "today's data" without a strategy for late arrivals will silently lose them. Watermarks, reprocessing windows, and lookback patterns are the design — not "we'll handle it if it happens." |
| **Configuration as code beats UI-based pipelines** | Pipelines defined in a web UI cannot be diffed, reviewed, version-controlled, or tested in isolation. Pipelines defined in code can. This is the same argument as IaC — the pipeline must be reproducible from source. |
| **Pipelines need observability separate from application observability** | Run duration, task success rate, data volume per run, freshness — these are first-class metrics. Pipelines that report only via "the alert fired" are unmanageable; the team learns of degradation only after impact. |

**Handy's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **Analytics engineering is software engineering** | SQL transformations are code: tested, version-controlled, peer-reviewed, refactored with confidence. "Just SQL" attitudes produce the analytics equivalent of untested spaghetti — works today, regresses silently, blames the data when it doesn't. |
| **Models are layered: staging → intermediate → marts** | Staging models (lightly cleaned 1:1 with sources). Intermediate models (joins, reusable building blocks). Mart models (consumer-facing, business-grained, denormalized). Models that skip layers (mart referencing source directly, mart joining many marts) make refactoring brittle — change one piece and downstream effects are unpredictable. |
| **Tests catch the schema; tests catch the data** | Schema tests (`unique`, `not_null`, `accepted_values`, `relationships`) catch shape regressions. Data tests (singular `.sql` files asserting business rules) catch semantic regressions. A dbt project with no tests is one that cannot refactor safely. |
| **Sources, refs, and seeds are the dependency graph** | `{{ source('raw', 'users') }}` and `{{ ref('stg_users') }}` are how dbt knows the DAG of models. Hardcoded table names (`FROM raw.users`) bypass the graph — incremental builds, freshness checks, lineage, and dependency-aware testing all break. |
| **Materialization is a deliberate tradeoff** | `view` (cheap to build, expensive to query, always fresh). `table` (cheap to query, full rebuild on every run). `incremental` (cheap to query, expensive to design — must define `unique_key`, `merge_update_columns`, late-arriving-data handling). `ephemeral` (CTE inlined, no warehouse object). New models default to `view`; `table` for stable but small; `incremental` for large and append-mostly. |
| **Documentation lives with the model** | Column descriptions, model purpose, ownership in `schema.yml` next to the model. Documentation in a wiki diverges; documentation in code travels with refactors and can be enforced (dbt has tests for missing docs). |
| **The semantic layer is the contract** | Defining metrics (revenue, MAU, churn) once in the semantic layer (dbt's MetricFlow, LookML, Cube) means consumers (BI tools, notebooks, reverse-ETL) compute them consistently. Each tool computing its own version of "active user" produces five different numbers that all claim to be authoritative. |

**Sculley's key positions:**

| Position | What it means in practice |
|----------|-----------------------------|
| **CACE — Changing Anything Changes Everything** | In ML systems, no input is independent. Changing the training data distribution, a feature's encoding, a hyperparameter, the random seed, or even the order of training examples can change the model's behavior in production. The implication: every change needs evaluation, every model needs versioning, and "small fix" is a vocabulary that doesn't apply. |
| **Training/serving skew is the most common production ML bug** | Features computed one way in training (Pandas during the notebook session) and computed differently in serving (Java service reading from a different store) produce a model that performs well on offline metrics and worse than its predecessor in production. Eliminate by computing features through the *same code path* in training and serving — a feature store or a shared library, not a "transcribed" reimplementation. |
| **Feedback loops produce silent quality collapse** | A model whose predictions influence the data it's trained on (recommendation systems, content moderation, ranking) is in a feedback loop. The loop amplifies biases and reduces diversity over time without any single deploy being the cause. Detection requires holding out a control population that doesn't receive the model's predictions; mitigation requires deliberate exploration. |
| **Glue code is the dominant maintenance cost** | Production ML systems are a small amount of model code surrounded by enormous amounts of data acquisition, feature serving, monitoring, infrastructure, and configuration. Underestimating this — measuring "ML engineering effort" by lines of model code — produces systems that ship and then collapse under their own maintenance burden. |
| **Undeclared consumers create implicit contracts** | When a model's output is published (logged, written to a table, exposed via an endpoint), unknown consumers downstream will start depending on it. A model retrain that changes the output distribution silently breaks those consumers. Either declare the contract (versioned model outputs, schema documentation, deprecation policies) or accept that you cannot change the model without coordination you can't enumerate. |
| **Model versioning and reproducibility are non-negotiable** | Every deployed model artifact must be traceable to the exact training code, training data snapshot, hyperparameters, random seed, and evaluation result that produced it. Without this, you cannot reproduce a model from history, debug a regression, or comply with audit requirements. Tools (MLflow, DVC, Weights & Biases) exist; the discipline is what makes them work. |
| **Drift is a first-class telemetry signal** | Production data distributions shift over time; the model's offline accuracy at training time stops matching its online performance. Monitor input feature distributions, output distributions, and (where ground truth is delayed but available) realized accuracy. Models without drift detection regress silently. |

*Synthesis:* Beauchemin evaluates whether the orchestration layer is *reliable as a mechanism* — idempotent tasks, partitioned inputs and outputs, code-defined pipelines, late-arrival strategies, observable runs. Handy evaluates whether the SQL transformation layer is *engineered as software* — layered models, tested at the schema and data levels, materialization chosen deliberately, documentation enforced. Sculley evaluates whether the ML layer is *operable in production over time* — training/serving parity, versioned artifacts, drift monitoring, declared contracts, feedback-loop awareness. A pipeline can be Beauchemin-correct (idempotent, backfillable, observed) but Handy-broken (no model tests, materialization chosen by default, models referencing sources directly); a dbt project can be Handy-correct (layered, tested, documented) but Beauchemin-broken (non-idempotent SQL, no partitioning strategy); an ML system can be both, and still Sculley-broken (training/serving skew, no versioning, undeclared consumers). The three lenses do not substitute for one another.

---

## Review Dimensions

---

### Dimension 44: Pipeline Orchestration & Functional Data Engineering
*Beauchemin*

| Hazard | What to look for |
|--------|-----------------|
| **Non-idempotent task** | Task that `INSERT`s without deduplication, sends a notification, increments a counter, or otherwise produces divergent state on second execution. Backfill, retry, and replay become unsafe. |
| **Hardcoded "today" / `datetime.now()` in task logic** | Task using wall-clock current time instead of the pipeline's logical execution date (`execution_date` / `logical_date` / `data_interval_start`). Backfilling yesterday's run today processes today's data. |
| **DAG module performing work at import time** | Module-level DB queries, API calls, or expensive computation in a DAG file. Airflow / Dagster scans DAG files frequently — every scan triggers the side effect. |
| **Task writes to a mutable destination instead of a partition** | `TRUNCATE customers; INSERT ...` style instead of writing to `customers/load_date=2026-05-28/`. Sequential runs collide; parallel runs corrupt; backfill cannot reproduce historical state. |
| **Task reads "current state" instead of a snapshot** | Task that reads from a source table without time-bounding the read (`SELECT * FROM events WHERE ...` with no date filter). Result depends on when the task ran, not on the logical date it claims to represent. |
| **`catchup=True` (Airflow default historically) without a backfill plan** | DAG newly deployed with `catchup=True` and a start date months in the past — the scheduler queues a year of runs immediately. Explicit `catchup=False` for new DAGs; deliberate backfill with `airflow dags backfill` when needed. |
| **XCom carrying large payloads** | Tasks passing dataframes, file contents, or large JSON via XCom. XCom is for orchestration metadata (paths, keys, small flags); large data goes through the data layer (S3 paths, table names, partition keys). |
| **Branching operator with asymmetric downstream coverage** | `BranchPythonOperator` with paths that skip required downstream tasks. Skipped state propagates; downstream tasks that should always run get skipped. Use trigger rules (`all_done`, `none_failed`) deliberately. |
| **Sensor without timeout** | `S3KeySensor`, `ExternalTaskSensor`, etc. waiting indefinitely without `timeout` or `soft_fail`. Blocks worker slots; pool contention escalates. |
| **Task retry without exponential backoff or attempt limit** | `retries=999, retry_delay=timedelta(seconds=1)` or equivalent. Retry storm on a sustained downstream outage. |
| **Task ID changes across deploys** | Renamed task IDs in an existing DAG. Run history breaks; XCom continuity breaks; the new ID has no prior runs. Either keep the ID stable or version the DAG. |
| **No SLA, no failure alerting** | DAG with no `sla` / `on_failure_callback` / alerting integration. Failures noticed only when downstream consumers complain. |
| **Pool / queue contention not configured** | Many concurrent tasks hitting the same downstream resource (database, API, warehouse slot) without a pool limiting concurrency. Self-DoS of the resource the pipeline depends on. |
| **Late-arriving data without lookback window** | Pipeline processing strictly "today's partition" with no provision for events that arrive late — late arrivals are silently dropped or attributed to the wrong day. Define the lookback window deliberately. |
| **Configuration in DAG body instead of variables / connections / config files** | Hardcoded connection strings, paths, environment-specific URLs in DAG Python. Cannot promote across environments without code edits. |

---

### Dimension 45: Analytics Engineering & dbt Discipline
*Handy*

| Hazard | What to look for |
|--------|-----------------|
| **Model without tests** | A `models/.../my_model.sql` with no entry in `schema.yml`, or an entry without `tests:`. Refactoring or upstream schema change regresses silently. At minimum: `unique` + `not_null` on the primary key. |
| **`SELECT *` in any layer** | `SELECT * FROM {{ ref('upstream') }}` in staging or downstream. Upstream column addition propagates; downstream depending on column count or order breaks. List columns explicitly. |
| **Hardcoded source table** | `FROM raw_schema.events` instead of `{{ source('raw', 'events') }}`. dbt's dependency graph, freshness checks, source documentation, and lineage all lose the edge. |
| **Reference to another mart from a mart** | `fct_orders` SELECTing from `fct_customer_summary`. Marts should consume from intermediate / staging, not other marts. Cross-mart references create dependency cycles and make refactoring brittle. |
| **Skipping layers** | A mart model SELECTing directly from `{{ source(...) }}` with no staging layer. Naming, type-coercion, deduplication, and renames are now scattered across marts. |
| **Materialization chosen by default** | All models `view` because no one set materialization, or all `table` because someone added it once and copied. Materialization is a tradeoff; reach for each one deliberately based on query frequency, build cost, and freshness requirements. |
| **Incremental model missing `unique_key`** | `{{ config(materialized='incremental') }}` with no `unique_key` and no `merge` strategy. New rows append; updates to existing rows produce duplicates. |
| **Incremental model with no late-arriving-data window** | Incremental model with `WHERE event_date > (SELECT MAX(event_date) FROM {{ this }})` — events that arrive after their event_date pass the watermark and are dropped. Use a lookback window or process by load_date. |
| **Tests run only post-merge** | dbt tests configured to run on a schedule or post-deploy but not as a required PR check. Regressions reach main and are detected hours later. |
| **No source freshness declared** | `sources` defined without `freshness:` thresholds. Stale source data goes unnoticed; downstream models compute over old facts and look correct. |
| **Macro reinventing dbt-utils / dbt-expectations** | Custom `generate_surrogate_key` / `date_spine` / `unpivot` / `pivot` / `expression_is_true` macros when the packages already provide tested versions. |
| **Singular tests duplicating built-in tests** | A `tests/` directory full of `.sql` files asserting `COUNT(*) FROM ... WHERE col IS NULL = 0` for things that should be `not_null` schema tests. Singular tests are for business rules built-in tests can't express. |
| **Hardcoded values that should be variables** | Magic dates, magic IDs, environment-specific values in model SQL. Use `vars` in `dbt_project.yml` (or `target.name` for environment-specific behavior). |
| **No documentation on columns** | `schema.yml` listing columns without descriptions. The dbt docs site renders empty fields; downstream consumers (BI tools, analysts) have no source of truth. |
| **Cross-database SQL without dialect handling** | SQL using Postgres-specific functions in a model that also runs on Snowflake (or vice versa). Use `{{ adapter.dispatch }}` or accept the lock-in deliberately. |
| **Snapshot strategy chosen without thought** | `strategy='timestamp'` requires a reliable updated_at; `strategy='check'` enumerates the columns to watch. Picking by default produces incorrect SCD-2 history. |
| **Surrogate keys via raw concatenation** | `MD5(CONCAT(a, b))` rolled by hand instead of `{{ dbt_utils.generate_surrogate_key([...]) }}`. The macro handles null-safety, dialect differences, and the canonical hash function. |
| **Model referenced by external consumer with no contract** | A mart consumed by a BI tool or reverse-ETL with no `model contracts` (dbt 1.5+) declaring its column-level shape. Schema changes break consumers silently. |

---

### Dimension 46: ML Systems Discipline (Training/Serving, Versioning, Drift)
*Sculley*

| Hazard | What to look for |
|--------|-----------------|
| **Training/serving skew** | Feature computed in a Pandas notebook during training, reimplemented in Java/Python service code for serving. Eventually the two implementations diverge — production model sees subtly different features than the one trained. Compute features through one shared code path (feature store or library imported by both). |
| **Training-time feature using future information** | A feature like `customer_lifetime_value` computed from data that, at the moment the prediction would have been made, didn't yet exist. The model looks good in offline evaluation; in production it has no signal. Audit every feature's "as-of" semantics. |
| **No random seed pinned in training** | `RandomForestClassifier()` / `train_test_split(...)` with no `random_state`. Re-running training produces a different model. Reproducibility, A/B comparisons, and bisection become impossible. |
| **Train/validation/test leakage** | Test set rows present in training (deduplication missed); features fitted (scaler, encoder, imputer) on the full dataset before split; time-series split done as random split. Offline accuracy inflates; production performance regresses. |
| **No model versioning / registry** | Models deployed without traceable lineage to training code, data snapshot, hyperparameters, and evaluation result. Cannot reproduce, cannot bisect, cannot audit. Use MLflow / DVC / a model registry. |
| **No baseline metric** | A new model deployed with no comparison to the existing baseline (or to a trivial baseline — predict the majority class, predict the average). "It's accurate" is not a metric; "it's 8 points better than the current production model on the same holdout" is. |
| **No drift monitoring in production** | Production model with no monitoring of input feature distributions, output distributions, or realized accuracy. Performance regression is detected by user complaints, not by telemetry. |
| **No feedback-loop control** | A recommender / ranker / moderation model whose predictions influence the data it will be retrained on, with no holdout / control population not receiving the model's output. The loop amplifies biases over generations of retraining. |
| **Undeclared output consumers** | Model outputs logged to a table or exposed via endpoint with no declared consumer contract. Downstream pipelines, dashboards, or features start depending on the output shape; retrain that changes the shape breaks them silently. |
| **Glue code dominates with no abstraction** | Training pipeline of hundreds of lines of Pandas indexing, dict munging, file path stitching, and conditional handling — with no library abstraction. The 50 lines of "model" surrounded by 2000 lines of glue. The glue is where the bugs and the maintenance cost live; treat it as code. |
| **Feature stores bypassed during training** | A feature store deployed for serving, but the training pipeline reads features by querying the warehouse directly instead of from the store. The two paths diverge; you ship the skew you tried to prevent. |
| **Training data snapshot not preserved** | Training pipeline reads "the current state of the warehouse" with no snapshot. Re-running training a week later produces a different model trained on different data. Snapshot the training data with the model artifact. |
| **Model that requires retraining on every code change** | Model code coupled to specific data shapes, library versions, or environment variables such that any change requires a full retrain. CACE in action; reduce coupling by isolating the model from infrastructure churn. |
| **Hyperparameters in code, not config** | Hyperparameter values inline in the training script with no externalization. Hyperparameter sweeps require code edits; "what hyperparameters did we use for v3?" requires git archaeology. |
| **No evaluation on subpopulations** | Model evaluated only on aggregate metrics (overall accuracy / AUC). Per-subgroup performance (by tenant, region, demographic, segment) hides regressions in tail populations. Aggregate metrics can improve while specific populations regress. |
| **Direct production prediction without shadowing or canary** | A new model deployed full-traffic without a shadow phase (compute predictions but don't use them) or canary (small fraction of traffic). The first production failure mode is the user's. |
| **No way to roll back a model** | New model deployed in place of old, with no preserved artifact for the prior model. Rollback requires retraining the old version — by which time the data has changed. |

Beauchemin's design question: for every task in this pipeline, can you re-run it for an arbitrary historical date and get the same output that the original run produced? If not, the task is not idempotent, and backfill is dangerous, not just inconvenient.

Handy's design questions: for every model in this dbt project, what tests would fail if its primary key duplicated, if its source schema added a column, or if a join cardinality changed? If "none" — the model isn't engineered, it's prototyped. For every metric exposed to BI tools, where is its single definition?

Sculley's design questions: for every feature this model uses in production, is it computed by the same code path that produced it during training? If not, name the divergence and assume it's already producing skew. For the production model running right now, can you point to the training data snapshot, code commit, hyperparameters, random seed, and offline evaluation result that produced it? If any are missing, the deployment is undocumented and unreproducible.
