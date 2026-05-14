.DEFAULT_GOAL := help
PYTHON := python -m harness

.PHONY: help init forge score submit review finish debug \
        forge-task task finish-task debug-task \
        index-status index-rebuild status stats

help:
	@echo ""
	@echo "  Single-spec workflow:"
	@echo "    make forge   TASK='description'    Explore + write spec"
	@echo "    make review  SPEC=spec-name         Review spec before submit"
	@echo "    make submit  SPEC=spec-name         Run spec through harness"
	@echo "    make finish  RUN=spec-name          Move output + open PR"
	@echo "    make debug   RUN=spec-name          Debug escalated spec"
	@echo ""
	@echo "  Multi-spec workflow:"
	@echo "    make forge-task FEATURE='description'  Explore + write task DAG"
	@echo "    make task        TASK=task-name         Run full task (auto-resumes checkpoint)"
	@echo "    make task-reset  TASK=task-name         Clear checkpoint, force full re-run"
	@echo "    make finish-task RUN=task-name          Move outputs + open PR"
	@echo "    make debug-task  RUN=task-name          Debug escalated task"
	@echo ""
	@echo "  Utility:"
	@echo "    make status                         Recent runs"
	@echo "    make stats                          Failure memory statistics"
	@echo ""

init:
	$(PYTHON) init

# ── Single-spec ───────────────────────────────────────────────────────────────

forge:
	@test -n "$(TASK)" || (echo "Usage: make forge TASK='description'"; exit 1)
	$(PYTHON) forge $(TASK)

score:
	@test -n "$(SPEC)" || (echo "Usage: make score SPEC=name"; exit 1)
	$(PYTHON) score $(SPEC)

review:
	@test -n "$(SPEC)" || (echo "Usage: make review SPEC=name"; exit 1)
	$(PYTHON) review $(SPEC)

submit:
	@test -n "$(SPEC)" || (echo "Usage: make submit SPEC=name"; exit 1)
	$(PYTHON) submit $(SPEC)

finish:
	@test -n "$(RUN)" || (echo "Usage: make finish RUN=name"; exit 1)
	$(PYTHON) finish $(RUN)

debug:
	@test -n "$(RUN)" || (echo "Usage: make debug RUN=name"; exit 1)
	$(PYTHON) debug $(RUN)

# ── Multi-spec task ───────────────────────────────────────────────────────────

forge-task:
	@test -n "$(FEATURE)" || (echo "Usage: make forge-task FEATURE='description'"; exit 1)
	$(PYTHON) forge-task $(FEATURE)

task:
	@test -n "$(TASK)" || (echo "Usage: make task TASK=name"; exit 1)
	$(PYTHON) task $(TASK)
task-reset:
	@test -n "$(TASK)" || (echo "Usage: make task-reset TASK=name"; exit 1)
	$(PYTHON) task-reset $(TASK)


finish-task:
	@test -n "$(RUN)" || (echo "Usage: make finish-task RUN=name"; exit 1)
	$(PYTHON) finish-task $(RUN)

debug-task:
	@test -n "$(RUN)" || (echo "Usage: make debug-task RUN=name"; exit 1)
	$(PYTHON) debug-task $(RUN)

# ── Utility ───────────────────────────────────────────────────────────────────

index-status:
	$(PYTHON) index-status

index-rebuild:
	$(PYTHON) index-rebuild

sandbox-status:
	$(PYTHON) sandbox-status

sandbox-build:
	$(PYTHON) sandbox-build $(LANG)

status:
	$(PYTHON) status

stats:
	$(PYTHON) stats
